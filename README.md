# PreAgent Project

## Project Overview
PreAgent is a project for forecasting and data scraping from various prediction markets and forecasting platforms.

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
