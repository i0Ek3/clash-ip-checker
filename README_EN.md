# 🚀 Clash Node Automator (Auto-IPCheck)

[中文](README.md) | [English](README_EN.md)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)

An intelligent automation tool for **Clash Verge** (and compatible cores) that automatically tests your proxy nodes, checks their IP purity/risk score via [IPPure](https://ippure.com/), and renames them with useful indicators (Bot Score, IP Risk, Native/Broadcast status).

![Demo Image](assets/clash-node-checked.png)

> **Note**: This tool uses **Playwright** for accurate browser-based fingerprinting detection, ensuring the results match what a real user would see.

## ✨ Features

- **Auto-Switching**: Automatically cycles through your Clash proxies.
- **Deep IP Analysis**: Checks IP Pure Score, Bot Ratio, IP Attributes (Native/Data Center), and Source.
- **Smart Filtering**: Skips invalid nodes (e.g., "Expire Date", "Traffic Reset") automatically.
- **Config Injection**: Generates a new Clash Config (`_checked.yaml`) with emojis and stats appended to node names.
- **Global Mode Force**: Temporarily forces Clash into Global mode for accurate testing.

## 🛠️ Prerequisites

- **Python 3.10+**
- **Clash Verge** (or any Clash client with External Controller enabled)
- **Playwright** (for browser automation)

## 📦 Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/yourusername/clash-automator.git
    cd clash-automator
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    playwright install chromium
    ```

3.  **Configure**
    - Duplicate `config.yaml.example` and rename it to `config.yaml`.
    - Edit `config.yaml` and fill in your details:
        - `yaml_path`: The absolute path to your current Clash configuration file.
        - `clash_api_secret`: Your API key (if any).

## 🚀 Usage

1.  Open your Clash Client (e.g., Clash Verge), switch to the profile you want to test, get its absolute YAML path, and configure `yaml_path` in `config.yaml`.
    ![Get YAML Path](assets/clash-open-yaml.png)
    ![Path via VSCode](assets/clash-open-yaml-vscode.png)
    ![Path via Notepad](assets/clash-open-yaml-jsb.png)
2.  Enable **External Controller** in Settings.
3.  Run the script:
    ```bash
    python clash_automator.py
    ```
4.  The script will:
    - Connect to Clash API.
    - Switch to "Global" mode.
    - Test each proxy one by one.
    - Generate a new file named `your_config_checked.yaml`.
5.  Import the new `_checked.yaml` into Clash to see the results!

## 📝 Output Example

Your proxy nodes will be renamed to provide instant visibility into their quality:

### 🔍 Result Interpretation

Format: `【🔵🔴 Attributes|Source】`

*   **1st Emoji (🔵)**: **IP Purity Score** (Lower is better, looks more like a real user)
*   **2nd Emoji (🔴)**: **Bot Score** (Lower is better, less likely to be blocked)
*   **Attributes**: Native IP, Data Center, Residential IP, etc.
*   **Source**: IP Location or ISP

#### 📊 Score Legend

| Range | Emoji | Meaning | Recommendation |
| :--- | :---: | :--- | :--- |
| **0 - 10%** | ⚪ | **Excellent** | Extremely pure, suitable for all uses |
| **11 - 30%** | 🟢 | **Great** | Suitable for strict risk controls |
| **31 - 50%** | 🟡 | **Good** | Normal browsing, most services available |
| **51 - 70%** | 🟠 | **Moderate** | May be blocked by strict sites |
| **71 - 90%** | 🔴 | **Bad** | Frequent CAPTCHAs, high risk |
| **> 90%** | ⚫ | **Terrible** | Likely blocked by high-security sites |

#### 🏷️ Attribute Tags

*   **Native**: IP belongs to a local ISP. Best for streaming unlocking (Netflix, Disney+).
*   **Data Center**: Hosted on cloud providers. Fast but often blocked by streaming.
*   **Broadcast**: IP location does not match registration country.

## ⚙️ Configuration

See `config.yaml.example` for all available options.

## 🤝 Contributing

Contributions are welcome! Please submit a Pull Request.

## ⚠️ Disclaimer

This tool is for educational and testing purposes only. Use it responsibly and in accordance with the terms of service of the proxies and websites you access.
