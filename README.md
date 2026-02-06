# LexiGuard - Multilingual Legal Document Analyzer

LexiGuard is a web-based AI tool built for a hackathon to demystify complex legal documents. It helps users in India understand rental agreements, loan contracts, and terms of service by providing summaries, risk analysis, and actionable checklists in multiple languages.

---

## ✨ Features

-   **Multi-Document Support:** Analyzes Rental Agreements, Loan Contracts, and Terms of Service.
-   **User-Controlled Analysis:** Users select the document type for a tailored summary.
-   **Proactive Assistance:**
    -   **AI-Generated Summary:** Provides a clear, simple summary of key points.
    -   **Risk Radar:** Highlights potentially risky or unfavorable clauses.
    -   **Actionable Checklist:** Generates a practical checklist of next steps for the user.
-   **Multilingual Interface:** Delivers analysis in English, Hinglish, Hindi, Telugu, Tamil, and Gujarati.
-   **Interactive Q&A:** Allows users to ask specific questions about the document text.

---

## 🛠️ Tech Stack

-   **Backend:** Python, Flask
-   **AI:** Google Gemini API (via `google-generativeai` SDK)
-   **Frontend:** HTML, CSS, JavaScript
-   **PDF Parsing:** PyPDF2

---

## 🚀 How to Run Locally

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/YOUR_USERNAME/lexiguard-hackathon.git](https://github.com/YOUR_USERNAME/lexiguard-hackathon.git)
    cd lexiguard-hackathon
    ```
2.  **Set up the Backend:**
    ```bash
    cd backend
    python -m venv venv
    # Activate the virtual environment
    # Windows: venv\Scripts\activate
    # macOS/Linux: source venv/bin/activate
    pip install -r requirements.txt
    ```
3.  **Add your API Key:**
    -   Create a file named `.env` inside the `backend` folder.
    -   Add your Google Gemini API key to it: `GEMINI_API_KEY="YOUR_API_KEY_HERE"`

4.  **Run the application:**
    ```bash
    python app.py
    ```
5.  Open your browser and go to `http://127.0.0.1:5000`.

---

*Note: You will need to create a `requirements.txt` file for these instructions to work. See the next step.*
