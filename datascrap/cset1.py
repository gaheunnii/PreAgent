# https://www.infer-pub.com/

# Standard library imports
import argparse
import datetime
import json
import logging
import os
import random
import time

# Related third-party imports
import jsonlines
from selenium.webdriver.common.by import By

# Local application/library-specific imports
from utils import data_scraping,time_utils
from configs.keys import keys

logger = logging.getLogger(__name__)
MAX_CONSECUTIVE_NOT_FOUND = 1000
# Writing to file for debugging purposes. It will be deleted once the script is done.
FILE_PATH = "cset_dump.jsonl"
# Use your own executable_path (download from https://chromedriver.chromium.org/).
CHROMEDRIVER_PATH = keys.get("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
CSET_EMAIL = keys["EMAIL"]
CSET_PASSWORD = keys["GJOPEN_CSET_PASSWORD"]

def getcommunity(tdata):
    s='['
    for item in tdata:
        if item[-1][1] is None:
            continue
        s+='["%s", %.4f],'%(time_utils.extract_date(item[-2][1]),float(item[-1][1])/100.0)
    s=s[:-1]+']'
    return s

def main(n_days):
    """
    Scrape, process, and upload question data from CSET (https://www.infer-pub.com/)

    Args:
        n_days (int): Number of days to look back for questions.

    Returns:
        list: A list of processed question data.
    """
    driver = data_scraping.initialize_and_login(
        signin_page="https://www.infer-pub.com/users/sign_in",
        email=CSET_EMAIL,
        password=CSET_PASSWORD,
        executable_path=CHROMEDRIVER_PATH,
    )

    question_counter = 0
    consecutive_not_found_or_skipped = 0
    while True:
        print(question_counter)
        question_counter += 1
        url = f"https://www.infer-pub.com/questions/{question_counter}"

        try:
            driver.get(url)
            trend_graph_element = driver.find_element(
                By.CSS_SELECTOR,
                "div[data-react-class='FOF.Forecast.ResolutionForm']",
            )
            props = json.loads(trend_graph_element.get_attribute("data-react-props"))
            props["extracted_articles_urls"] = data_scraping.get_source_links(
                driver, url
            )
            trend_graph_element1 = driver.find_element(
                By.CSS_SELECTOR,
                "div[data-react-class='FOF.Forecast.QuestionTrendGraph']",
            )
            props1 = json.loads(trend_graph_element1.get_attribute("data-react-props"))
            for k in props1.keys():
                props[k]=props1[k]
            with jsonlines.open(FILE_PATH, mode="a") as writer:
                writer.write(props)
            consecutive_not_found_or_skipped = 0
            print('success')
        except BaseException:
            if data_scraping.question_not_found(driver):
                logger.info(f"Question {question_counter} not found")
            else:
                logger.info(f"Skipping question {question_counter}")
            consecutive_not_found_or_skipped += 1
            if consecutive_not_found_or_skipped > MAX_CONSECUTIVE_NOT_FOUND:
                logger.info("Reached maximum consecutive not found.")
                break
            print('failed')
        time.sleep(random.uniform(0, 2))  # random delay between requests

    data = []
    with open(FILE_PATH, "r") as file:
        for line in file:
            json_line = json.loads(line)
            data.append(json_line)

    # Remove duplicated dicts
    unique_tuples = {data_scraping.make_hashable(d) for d in data}
    all_questions = [data_scraping.unhashable_to_dict(t) for t in unique_tuples]

    if n_days is not None:
        date_limit = datetime.datetime.now() - datetime.timedelta(days=n_days)
        date_upper_limit = datetime.datetime.now()
    else:
        date_limit = datetime.datetime(2024, 5, 1)
        date_upper_limit = datetime.datetime(2025,4,1)
    all_questions = [
        q
        for q in all_questions
        if (datetime.datetime.fromisoformat(q["question"]["created_at"][:-1])>= date_limit)\
            and(datetime.datetime.fromisoformat(q["question"]["created_at"][:-1])< date_upper_limit)
    ]

    logger.info(f"Number of cset questions fetched: {len(all_questions)}")

    fbdata=[]
    fmdata=[]

    for i in range(len(all_questions)):
        tdata={}
        tdata['url']="https://www.infer-pub.com/questions/" + str(
            all_questions[i]["question"]["id"]
        )
        tdata['question'] = all_questions[i]["question"]["name"]

        tdata['date_begin'] = time_utils.extract_date(all_questions[i]["question_starts_at"])
        if all_questions[i]["question"]["state"] != "resolved":
            tdata["resolution"] = "Not resolved."
            tdata["is_resolved"] = False
            tdata['date_close'] = None
            tdata['date_resolve_at']=None
        else:
            tdata["resolution"] = all_questions[i]["question"]["answers"][0][
                "probability"
            ]
            tdata["is_resolved"] = True
            tdata['date_close'] = time_utils.extract_date(all_questions[i]["question"]['closed_at'])
            tdata['date_resolve_at'] = time_utils.extract_date(all_questions[i]["question"]['resolved_at'])
        tdata["data_source"] = "cset"
        tdata["question_type"] = "binary"
        tdata["background"] = all_questions[i]["question"]["description"]
        tdata['resolution_criteria']="Not applicable/available for this question."
        tdata['extracted_urls']=all_questions[i]["extracted_articles_urls"]
        # print(i)
        # print(all_questions[i])
        # print(all_questions[i]['chart'].keys())
        # print(list(all_questions[i]['chart']['datasets'].keys())[0][1][0])
        # print(all_questions[i]['chart']['datasets'])
        tdata['community_predictions']=getcommunity(list(all_questions[i]['chart']['datasets'].keys())[0][1])
        answer_set = set(
            [answer["name"] for answer in all_questions[i]["question"]["answers"]]
        )
        if answer_set == {"Yes", "No"} or answer_set == {"Yes"}:
            tdata["question_type"] = "binary"
            fbdata.append(tdata)
        else:
            tdata["question_type"] = "multiple_choice"
            fmdata.append(tdata)
    data_root_dir = keys.get("DATA_ROOT_DIR", "./data")
    binary_path = os.path.join(data_root_dir, "cset", "binary.json")
    multi_path = os.path.join(data_root_dir, "cset", "multi.json")
    
    # Create directories if they don't exist
    os.makedirs(os.path.dirname(binary_path), exist_ok=True)
    os.makedirs(os.path.dirname(multi_path), exist_ok=True)
    
    with open(binary_path, 'w') as f:
        json.dump(fbdata, f)
    with open(multi_path, 'w') as f:
        json.dump(fmdata, f)

    # # Delete the file after script completion
    # if os.path.exists(FILE_PATH):
    #     os.remove(FILE_PATH)
    #     logger.info(f"Deleted the file: {FILE_PATH}")
    # else:
    #     logger.info(f"The file {FILE_PATH} does not exist")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch cset data.")
    parser.add_argument(
        "--n_days",
        type=int,
        help="Fetch markets created in the last N days",
        default=None,
    )
    args = parser.parse_args()
    main(args.n_days)
