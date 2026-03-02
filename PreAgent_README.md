# PreAgent

## A Multi-Agent Forecasting Framework for Binary Event Prediction

PreAgent is a structured multi-agent forecasting framework designed for
**binary real-world event prediction (Yes / No)**. The system transforms
traditional single large language model (LLM) inference into a modular,
controllable, and interpretable multi-agent collaborative decision
architecture.

The project targets forecasting questions with explicit time windows and
objectively verifiable outcomes, such as:

> "Will event X occur before time Y?"

------------------------------------------------------------------------

# 1. Background and Motivation

Binary event forecasting tasks are widely used in professional
prediction platforms. These questions typically exhibit the following
characteristics:

-   A Yes / No structure\
-   A clearly defined resolution date\
-   Objectively verifiable ground truth\
-   Quantifiable evaluation metrics

Although large language models demonstrate strong reasoning
capabilities, directly applying a single model to forecasting introduces
several limitations:

1.  Overconfidence under uncertainty\
2.  Hallucinated or weakly supported conclusions\
3.  Lack of access to real-time external information\
4.  Limited interpretability of the reasoning process\
5.  Inability to dynamically adapt strategy based on question complexity

PreAgent systematically addresses these challenges by introducing
structured multi-agent collaboration, retrieval-augmented reasoning,
debate mechanisms, and dynamic strategy routing.

------------------------------------------------------------------------

# 2. Overall System Architecture

Data Preparation → Strategy Selection → Retrieval & Reasoning → Decision
Aggregation → Evaluation & Logging

## System Architecture Diagram

                               ┌────────────────────────┐
                               │     Forecast Dataset   │
                               │ (Resolved Binary Qs)   │
                               └────────────┬───────────┘
                                            │
                                            ▼
                               ┌────────────────────────┐
                               │   Data Preprocessing   │
                               │ - Normalize Fields     │
                               │ - Extract URLs         │
                               │ - Filter Resolved      │
                               └────────────┬───────────┘
                                            │
                        ┌───────────────────┼───────────────────────┐
                        │                   │                       │
                        ▼                   ▼                       ▼
                 ┌───────────────┐   ┌────────────────┐   ┌────────────────┐
                 │ BaselineAgent │   │  DebateAgent   │   │    DynAgent    │
                 └───────┬───────┘   └───────┬────────┘   └────────┬───────┘
                         │                   │                        │
                         ▼                   ▼                        ▼
                 ┌───────────────┐  ┌───────────────────┐  ┌─────────────────┐
                 │ Retrieval +   │  │ Multi-Agent Debate│  │ Dynamic Routing │
                 │  Reasoning    │  │ (Debaters + Mod)  │  │ Decision Logic  │
                 └───────────────┘  └───────────────────┘  └─────────────────┘
                         │                   │                        │
                         └───────────────┬───┴───────────────┬────────┘
                                         ▼                   ▼
                                  ┌────────────────────────┐
                                  │  Decision Aggregation  │
                                  └────────────┬───────────┘
                                               ▼
                                  ┌────────────────────────┐
                                  │ Evaluation & Logging   │
                                  │ Accuracy / F1 / Matrix │
                                  └────────────────────────┘

The architecture separates the system into two core layers: the
**Functional Layer** and the **Strategy Layer**, enabling controlled
comparison and ablation analysis across different forecasting
strategies.

------------------------------------------------------------------------

# 3. Functional Module Design

## 3.1 SearchAgent (Information Retrieval)

Responsible for acquiring external evidence:

-   Generate search queries from the question\
-   Call search APIs\
-   Rank and filter results\
-   Extract structured evidence summaries

This module reduces hallucination and strengthens factual grounding.

------------------------------------------------------------------------

## 3.2 ReasoningAgent (Evidence-Based Reasoning)

Responsible for analyzing evidence and performing structured inference.

The system supports multiple reasoning personas, such as:

-   Optimistic analyst\
-   Conservative analyst\
-   Risk evaluator

Different agents provide diverse perspectives, improving reasoning
robustness and diversity.

------------------------------------------------------------------------

## 3.3 DecisionAgent (Decision Aggregation)

Responsible for:

-   Aggregating reasoning outputs from all agents\
-   Evaluating logical consistency\
-   Assessing evidence strength\
-   Producing the final Yes / No prediction

------------------------------------------------------------------------

# 4. Strategy Layer Design

PreAgent implements three core forecasting strategies.

## 4.1 BaselineAgent

-   Retrieval-augmented reasoning\
-   Single-pass inference\
-   Simple structure and computationally efficient

Used as the primary baseline for comparison.

------------------------------------------------------------------------

## 4.2 DebateAgent

-   Multiple reasoning agents analyze the same evidence\
-   Agents engage in multi-round critique and rebuttal\
-   A Moderator aggregates arguments and produces the final decision

This structured adversarial mechanism reduces single-perspective bias
and enhances robustness.

------------------------------------------------------------------------

## 4.3 DynAgent (Dynamic Strategy Agent)

-   Evaluates question complexity\
-   Dynamically decides whether to perform retrieval\
-   Dynamically decides whether to initiate debate\
-   Adjusts reasoning rounds accordingly

DynAgent balances predictive performance and computational cost, making
it suitable for large-scale forecasting scenarios.

------------------------------------------------------------------------

## 4.4 NoSearch Variants

Each strategy includes a corresponding NoSearch version:

-   BaselineAgent_NoSearch\
-   DebateAgent_NoSearch\
-   DynAgent_NoSearch

These variants remove external retrieval and rely solely on internal LLM
knowledge, enabling structural ablation analysis.

------------------------------------------------------------------------

# 5. Data and Preprocessing Pipeline

The system supports datasets consisting of resolved binary forecasting
questions, sourced from the following prediction platforms:

- **CSET** (Center for Security and Emerging Technology)
- **Good Judgment Open**
- **Manifold Markets**
- **Metaculus**

These datasets are collected through web scraping scripts located in the `datascrap/` directory. Each sample includes:

-   Question text\
-   Background information\
-   Resolution criteria\
-   Time window\
-   Ground truth label (0/1)

Preprocessing steps include:

-   Field normalization\
-   Time format standardization\
-   Invalid data filtering\
-   External link extraction\
-   Construction of structured datasets

Only resolved questions are retained for evaluation to ensure objective
benchmarking.

------------------------------------------------------------------------

# 6. Experimental Design

Experiments compare:

-   Retrieval vs. No Retrieval\
-   Single-agent vs. Multi-agent debate\
-   Fixed strategy vs. Dynamic strategy

Evaluation metrics include:

-   Accuracy\
-   Precision\
-   Recall\
-   F1 Score\
-   Confusion Matrix

Key observations:

1.  Dataset characteristics significantly affect agent performance.\
2.  Debate without retrieval may become overly conservative.\
3.  Retrieval is critical for policy-driven or dynamically evolving
    questions.\
4.  Dynamic routing improves efficiency under resource constraints.

------------------------------------------------------------------------

# 7. System Implementation

-   Programming Language: Python\
-   Multi-agent coordination framework\
-   LLM backend integration\
-   External search API integration\
-   Full reasoning trace logging\
-   Multi-GPU scheduling support

The system records:

-   Prompts\
-   Retrieved evidence\
-   Intermediate reasoning steps\
-   Final outputs\
-   Token usage statistics

Ensuring reproducibility and interpretability.

------------------------------------------------------------------------

# 8. Project Structure

    preagent/
    │
    ├── configs/            # Configuration files
    ├── data/               # Processed datasets
    ├── datascrap/          # Data scraping scripts
    ├── prompts/            # Prompt templates
    ├── utils/              # Utility functions
    ├── BaselineAgent.py
    ├── DebateAgent.py
    ├── DynAgent.py
    ├── main.py             # Entry point
    ├── multigpu.py         # Multi-GPU scheduler
    ├── run.sh              # Experiment scripts
    └── complog/            # Logs and reasoning traces

------------------------------------------------------------------------

# 9. Strengths

-   Modular multi-agent architecture\
-   Strategy-level ablation support\
-   Retrieval-augmented reasoning\
-   Structured and interpretable decision process\
-   Scalable execution framework

------------------------------------------------------------------------

# 10. Limitations

-   API quota limits restrict large-scale retrieval experiments\
-   Some datasets have limited sample sizes\
-   No statistical significance testing conducted\
-   Systematic error-type analysis not yet completed

------------------------------------------------------------------------

# 11. Conclusion

PreAgent demonstrates that transforming single-model inference into a
structured multi-agent collaborative decision system can significantly
enhance robustness, interpretability, and adaptability in binary event
forecasting tasks.

By integrating retrieval augmentation, multi-role debate, and dynamic
strategy routing, the framework provides a practical exploration of
multi-agent coordination for complex real-world decision-making
scenarios.

---

# 12. Getting Started

## Installation

### Prerequisites
- Python 3.7+
- pip

### Setup
1. Clone the repository
2. Install dependencies (if any)
3. Configure environment variables

## Configuration

### Environment Variables
The project uses environment variables for configuration. Create a `.env` file based on the `.env.example` template:

```bash
cp .env.example .env
```

Then edit the `.env` file to set your specific values:

- **API Keys**: Various API keys for different platforms
- **Proxy Settings**: Proxy configuration for network requests
- **Path Settings**: Paths for data storage and ChromeDriver

### Key Configuration Items

#### Proxy Settings
```
HTTP_PROXY=http://your-proxy:port
HTTPS_PROXY=http://your-proxy:port
```

#### Path Settings
```
DATA_ROOT_DIR=./data  # Directory for storing scraped data
CHROMEDRIVER_PATH=/usr/local/bin/chromedriver  # Path to ChromeDriver executable
```

## Usage

### Running the Project
```bash
python BasenoAgent.py --dataset cset --prompt detailed
```

### Data Scraping
The project includes scripts to scrape data from various platforms:
- `datascrap/gjopen1.py` - Scrape data from Good Judgment Open
- `datascrap/cset1.py` - Scrape data from CSET
- `datascrap/manifold.py` - Scrape data from Manifold Markets
- `datascrap/metaculus.py` - Scrape data from Metaculus

## Project Structure
- `configs/` - Configuration files
- `data/` - Scraped data
- `datascrap/` - Data scraping scripts
- `preagent_res/` - Results and logs
- `prompts/` - Prompt templates
- `utils/` - Utility functions

## Notes
- The `.env` file is excluded from version control (see `.gitignore`)
- Always keep your API keys and sensitive information secure
- Update the proxy settings according to your network environment
