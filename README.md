# PreAgent

## A Multi-Agent Forecasting Framework for Binary Event Prediction

PreAgent is a structured multi-agent forecasting framework for **binary real-world event prediction (Yes / No)**. It is designed for forecasting questions with explicit time windows and objectively verifiable outcomes, such as:

> “Will event X occur before time Y?”

Instead of relying on a single large language model (LLM) to make an end-to-end judgment, PreAgent organizes forecasting into a structured pipeline that combines evidence retrieval, agent-based reasoning, and final decision aggregation.

---

# 1. Background and Motivation

Binary event forecasting is widely used on professional prediction platforms. These questions usually have the following properties:

- A Yes / No outcome
- A clearly defined resolution date
- Objectively verifiable ground truth
- Quantifiable evaluation metrics

Although LLMs have strong reasoning ability, directly applying a single model to forecasting still introduces several limitations:

1. Overconfidence under uncertainty  
2. Hallucinated or weakly supported conclusions  
3. Limited access to up-to-date external information  
4. Limited interpretability of the reasoning process  
5. Difficulty adapting strategy to questions of different complexity  

PreAgent explores whether structured agent coordination can make forecasting more robust, interpretable, and controllable.

---

# 2. Overall System Architecture

**Common pipeline**  
Data Preparation → Strategy Selection → Retrieval / Reasoning → Decision Aggregation → Evaluation & Logging

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
                 ┌───────────────┐  ┌───────────────────┐  ┌──────────────────────────┐
                 │ Retrieval +   │  │ Multi-Agent Debate│  │ Dynamic Expert / Process  │
                 │  Reasoning    │  │ (Debaters + Mod)  │  │ Coordination Logic        │
                 └───────────────┘  └───────────────────┘  └──────────────────────────┘
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

The framework follows a common forecasting pipeline, while each strategy adopts a different internal agent organization and coordination mechanism.

For clarity, the “Functional Layer” and “Strategy Layer” in this project should be understood as **conceptual design abstractions** rather than a fully unified shared implementation across all agents. In practice, different strategies instantiate different agent roles and communication structures.

---

# 3. Conceptual Functional Modules

The project can be described through three conceptual functions that recur across the forecasting pipeline.

## 3.1 Retrieval

This stage is responsible for obtaining potentially relevant external evidence:

- Generate search queries from the forecasting question
- Call external search tools or APIs
- Filter and rank returned results
- Extract short evidence summaries

Its goal is to reduce unsupported reasoning and improve factual grounding.

## 3.2 Reasoning

This stage is responsible for analyzing question context and evidence.

Depending on the strategy, reasoning may be performed by:

- A single forecasting agent
- Multiple debating agents with different perspectives
- A dynamically coordinated set of expert-like agents

The exact implementation differs by strategy rather than being enforced through one identical shared module.

## 3.3 Decision Aggregation

This stage is responsible for producing the final Yes / No forecast by:

- Combining intermediate reasoning outputs
- Weighing evidence support and logical consistency
- Generating the final prediction

---

# 4. Strategy Layer Design

PreAgent implements three main forecasting strategies, along with NoSearch variants for ablation.

## 4.1 BaselineAgent

BaselineAgent represents the simplest retrieval-augmented forecasting setting.

- Uses external retrieval when enabled
- Performs relatively direct evidence-based reasoning
- Produces a final binary decision with a simple coordination structure

This agent serves as the main baseline for comparison.

## 4.2 DebateAgent

DebateAgent introduces structured multi-agent critique.

- Multiple agents analyze the same question or evidence
- Agents challenge, critique, or refine one another’s reasoning across rounds
- A moderator-like agent aggregates the discussion into a final decision

This design aims to reduce single-perspective bias through structured adversarial reasoning.

## 4.3 DynAgent

DynAgent is the most adaptive strategy in the project.

In the current implementation, DynAgent is better described as a **dynamic coordination mechanism** than as a fixed hand-crafted router. It organizes forecasting through iterative agent interaction, where the system may adjust the use of experts, discussion flow, and evidence collection according to the problem and intermediate reasoning state.

More specifically, DynAgent is intended to:

- adapt coordination according to question needs,
- reduce unnecessary multi-round interaction when possible,
- balance forecasting quality and computational cost.

To avoid overstating the implementation, DynAgent should be understood as **dynamic expert / process coordination** rather than a fully formalized complexity-scoring router.

## 4.4 NoSearch Variants

Each main strategy includes a corresponding NoSearch version:

- `BaselineAgent_nosearch.py`
- `DebateAgent_nosearch.py`
- `DynAgent_nosearch.py`

These variants disable external retrieval and rely only on the model’s internal knowledge and reasoning process. They are used for structural ablation analysis, helping separate the effect of **agent structure** from the effect of **external information access**.

---

# 5. Data and Preprocessing Pipeline

The project uses resolved binary forecasting questions collected from multiple forecasting platforms, including:

- **CSET**
- **Good Judgment Open (GJOpen)**
- **Manifold Markets**
- **Metaculus**

Each sample may include:

- Question text
- Background or description
- Resolution criteria
- Time window
- Ground-truth label (0/1)

Preprocessing includes:

- Field normalization
- Time-format standardization
- Invalid-sample filtering
- Optional extraction of external links or related references
- Construction of structured processed datasets for experiments

Only resolved questions are retained for evaluation so that predictions can be compared against objective outcomes.

---

# 6. Experimental Design and Results

## Experiment Setup

The experiments are designed to compare:

- Retrieval vs. No Retrieval
- Simpler vs. richer agent coordination
- Fixed strategy vs. more adaptive coordination

Evaluation metrics include:

- Accuracy
- Precision
- Recall
- F1 score
- Confusion-matrix-based analysis

## Important Evaluation Note

Due to search API quota constraints, retrieval-enabled experiments were conducted only on limited subsets in some settings. Therefore, current retrieval-based results should be interpreted as **preliminary evidence** rather than as fully scaled, strictly comparable final results.

For this reason, the tables below explicitly include question counts where subset evaluation was used.

## Experimental Results

### GJOpen Dataset

| Agent Type | Accuracy | Precision | Recall | F1 |
| --- | --- | ---: | ---: | ---: |
| Baseline_NoSearch | 0.9118 | 0.9333 | 0.8750 | 0.9032 |
| Debate_NoSearch | 0.8824 | 0.9615 | 0.7812 | 0.8621 |
| DynAgent_NoSearch | 0.9474 | 1.0000 | 0.8846 | 0.9388 |
| DynAgent | 0.9048 | 1.0000 | 0.7500 | 0.8571 |

### CSET Dataset

| Agent Type | Accuracy | Precision | Recall | F1 |
| --- | --- | ---: | ---: | ---: |
| Baseline_NoSearch | 0.7451 | 0.4000 | 0.6000 | 0.4800 |
| Debate_NoSearch | 0.8431 | 1.0000 | 0.2000 | 0.3333 |
| DynAgent_NoSearch | 0.7727 | 0.2222 | 0.4000 | 0.2857 |
| DynAgent | 0.7097 | 0.2222 | 0.5000 | 0.3077 |

## Key Findings

### 1. Dataset characteristics strongly affect forecasting behavior

Performance is much higher on GJOpen than on CSET. A plausible interpretation is that GJOpen contains more fact-bounded and structurally explicit questions, while CSET includes more policy-sensitive or time-sensitive questions that depend more heavily on external and current evidence.

### 2. More agents do not automatically improve no-retrieval forecasting

Under NoSearch settings, richer agent interaction does not always improve results. In some cases, multi-agent discussion can introduce extra conservatism or noise, especially when the model lacks enough background knowledge to support confident forecasting.

### 3. External evidence appears especially important for harder policy-oriented questions

The current results suggest that retrieval matters more for datasets like CSET, where internal model knowledge alone is less sufficient. However, because retrieval-enabled runs are still limited, this should be treated as an informed preliminary conclusion rather than a definitive claim.

### 4. Adaptive coordination may offer an efficiency-performance tradeoff

DynAgent is motivated by the idea that not all questions need the same degree of interaction. Preliminary runs suggest that adaptive coordination can sometimes preserve strong precision while avoiding unnecessary rounds, although more controlled large-scale evaluation is still needed.

---

# 7. System Implementation

The project is implemented in Python and combines:

- LLM-based agent reasoning
- External retrieval support
- Multi-agent communication / coordination logic
- Logging of prompts, evidence, and reasoning traces

The current codebase should be understood as a **research-oriented experimental framework**, not a fully standardized production system. Some conceptual modules described in this README are reflected more clearly at the design level than as one fully unified implementation shared by every strategy.

The system records:

- Prompts
- Retrieved evidence
- Intermediate reasoning traces
- Final outputs
- Token usage statistics

These logs support inspection, debugging, and experiment tracking.

Regarding execution utilities, the repository also contains scripts for experiment management and task scheduling. These utilities are best understood as support for batch experimentation rather than as a central algorithmic contribution.

---

# 8. Project Structure

```text
preagent/
│
├── configs/                  # Configuration files
├── data/                     # Processed datasets
├── datascrap/                # Data scraping scripts
├── prompts/                  # Prompt templates
├── utils/                    # Utility functions
├── BaselineAgent.py          # Baseline strategy with retrieval support
├── BaselineAgent_nosearch.py # Baseline ablation without retrieval
├── DebateAgent.py            # Debate-based strategy
├── DebateAgent_nosearch.py   # Debate ablation without retrieval
├── DynAgent.py               # Dynamically coordinated strategy
├── DynAgent_nosearch.py      # Dynamic ablation without retrieval
├── main.py                   # Main orchestration entry
├── multigpu.py               # Batch execution / scheduling utility
└── complog/                  # Logs and reasoning traces
```

---

# 9. Limitations

- Search API quota constraints restrict the scale of retrieval-enabled experiments
- Some reported retrieval results are based on subsets rather than full matched evaluations
- No statistical significance testing has been conducted yet
- Calibration of confidence / overconfidence has not been systematically evaluated
- Systematic error taxonomy and failure-case analysis remain incomplete
- Some parts of the codebase retain research-prototype characteristics rather than fully unified software abstractions

---

# 10. Conclusion

PreAgent explores how binary event forecasting can be transformed from single-model inference into a more structured multi-agent decision process.

Across baseline, debate-based, and dynamically coordinated settings, the project investigates how external evidence, coordination structure, and adaptive interaction may affect forecasting quality. While the current results are still partial in some retrieval-enabled settings, they suggest that structured coordination is a promising direction for improving robustness and interpretability in real-world forecasting tasks.

---

# 11. Getting Started

## Requirements

- Python 3.7+
- pip
- Access to the required model and search APIs if you want to run retrieval-enabled experiments

## Setup

1. Clone the repository
2. Install dependencies
3. Configure required environment variables or local configuration files

## Example Environment Configuration

Typical configuration may include:

- Model API credentials
- Search API credentials
- Optional proxy settings
- Local data paths

Example:

```bash
HTTP_PROXY=http://your-proxy:port
HTTPS_PROXY=http://your-proxy:port
DATA_ROOT_DIR=./data
CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
```

## Usage

Please update the exact command according to your local code entry and experiment setup. Based on the current repository files, likely entry points include:

```bash
python BaselineAgent.py
python DebateAgent.py
python DynAgent.py
```

For ablation experiments:

```bash
python BaselineAgent_nosearch.py
python DebateAgent_nosearch.py
python DynAgent_nosearch.py
```

`main.py` can also serve as an orchestration entry depending on your local setup.

## Notes

- Keep API keys and sensitive settings out of version control.
- Retrieval-enabled experiments may be limited by quota.
- Reported retrieval results in this README should be interpreted together with the subset-size notes above.
