import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
import docx # For reading .docx files
import fitz  # PyMuPDF for reading .pdf files

# --- SETUP AND CONFIGURATION ---

load_dotenv()
app = Flask(__name__)
CORS(app) 

try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Gemini API configured successfully.")
except Exception as e:
    print(f"Error configuring Gemini API: {e}")
    model = None

# --- HELPER FUNCTION FOR TEXT EXTRACTION ---

def extract_text_from_file(file):
    filename = file.filename
    text = ""
    temp_filepath = os.path.join("./", filename)
    file.save(temp_filepath)
    
    try:
        if filename.endswith(".pdf"):
            with fitz.open(temp_filepath) as doc:
                for page in doc:
                    text += page.get_text()
        elif filename.endswith(".docx"):
            doc = docx.Document(temp_filepath)
            for para in doc.paragraphs:
                text += para.text + "\n"
        else:
            os.remove(temp_filepath)
            return None, "Unsupported file type"
    except Exception as e:
        os.remove(temp_filepath)
        return None, f"Error extracting text: {e}"

    os.remove(temp_filepath)
    return text, None

# --- PROMPT TEMPLATES (UPGRADED) ---

PROMPTS = {
    "rental": """
    Act as 'Lexi,' an expert AI legal analyst for a user in India. You specialize in simplifying Indian residential rental agreements for tenants. Your tone must be clear, simple, and helpful. Analyze the provided text and YOU MUST ONLY output a single, valid JSON object.
    The JSON object must have: {"summary": "...", "keyDetails": [{"label": "Monthly Rent", "value": "..."}, {"label": "Security Deposit", "value": "..."}, {"label": "Agreement Duration", "value": "..."}, {"label": "Notice Period", "value": "..."}, {"label": "Rent Increase", "value": "..."}, ...], "redFlags": [{"clause": "...", "concern": "...", "severity": "..."}]}
    Here is the rental agreement text to analyze:
    ---
    {text}
    ---
    """,
    "loan": """
    Act as 'Lexi,' an expert AI legal analyst for a user in India. You specialize in simplifying Indian loan contracts for the BORROWER. Your tone must be clear, simple, and helpful. Analyze the provided text and YOU MUST ONLY output a single, valid JSON object.
    The JSON object must have: {"summary": "...", "keyDetails": [{"label": "Principal Amount", "value": "..."}, {"label": "Interest Rate", "value": "..."}, {"label": "Loan Tenure", "value": "..."}, {"label": "EMI / Repayment", "value": "..."}, {"label": "Prepayment Charges", "value": "..."}, ...], "redFlags": [{"clause": "...", "concern": "...", "severity": "..."}]}
    Instructions for Red Flags: Look for hidden fees, aggressive late payment penalties, clauses allowing the lender to unilaterally change terms, and ambiguous prepayment charges.
    Here is the loan contract text to analyze:
    ---
    {text}
    ---
    """,
    "tos": """
    Act as 'Lexi,' an expert AI legal analyst for a user in India. You are simplifying a 'Terms of Service' or 'Privacy Policy' document for a regular user. Your tone must be clear, simple, and helpful. Analyze the provided text and YOU MUST ONLY output a single, valid JSON object.
    The JSON object must have: {"summary": "...", "keyDetails": [{"label": "Data Collection", "value": "..."}, {"label": "Content Ownership", "value": "..."}, {"label": "Account Termination", "value": "..."}, {"label": "Arbitration Clause", "value": "..."}, ...], "redFlags": [{"clause": "...", "concern": "...", "severity": "..."}]}
    Instructions for Red Flags: Look for clauses that give the company broad rights to use user data, claim ownership of user-generated content, force binding arbitration, or allow them to change terms without clear notice.
    Here is the Terms of Service text to analyze:
    ---
    {text}
    ---
    """,
    # Add this inside the PROMPTS dictionary
"chat": """
Act as 'Lexi,' an AI legal analyst. You have already provided an initial analysis of the following legal document. Now, the user has a follow-up question. Your task is to answer the user's question based ONLY on the provided document text. Be concise and directly answer the question. If the answer is not in the document, say "I cannot find the answer to that question in the provided document." Do not use outside knowledge.

DOCUMENT TEXT:
---
{text}
---

USER'S QUESTION:
"{question}"
"""
}

# --- API ENDPOINT ---

@app.route("/analyze", methods=["POST"])
def analyze_document():
    if model is None: return jsonify({"error": "Gemini API not configured."}), 500
    if 'file' not in request.files: return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    doc_type = request.form.get("docType")

    if file.filename == '': return jsonify({"error": "No selected file"}), 400
    if not doc_type or doc_type not in PROMPTS: return jsonify({"error": "Invalid document type"}), 400

    document_text, error = extract_text_from_file(file)
    if error: return jsonify({"error": error}), 500
    if not document_text: return jsonify({"error": "Could not extract text"}), 400
        
    final_prompt = PROMPTS[doc_type].format(text=document_text)

    try:
        response = model.generate_content(final_prompt)
        cleaned_response_text = response.text.strip().replace("```json", "").replace("```", "").strip()
        json_response = json.loads(cleaned_response_text)
        print("Successfully analyzed document.")
        return jsonify({
    "analysis": json_response,
    "documentText": document_text
})
    except Exception as e:
        print(f"Error calling Gemini API or parsing JSON: {e}")
        return jsonify({"error": "Failed to analyze document with AI."}), 500
    
    # Add this new function before the if __name__ == "__main__": line

@app.route("/chat", methods=["POST"])
def handle_chat():
    if model is None:
        return jsonify({"error": "Gemini API not configured."}), 500

    data = request.get_json()
    document_text = data.get("documentText")
    question = data.get("question")

    if not document_text or not question:
        return jsonify({"error": "Document text and a question are required."}), 400

    try:
        prompt_template = PROMPTS["chat"]
        final_prompt = prompt_template.format(text=document_text, question=question)

        response = model.generate_content(final_prompt)

        # The chat response is simpler, so we just send back the text
        ai_answer = response.text.strip()

        print("Successfully answered chat question.")
        return jsonify({"answer": ai_answer})

    except Exception as e:
        print(f"Error during chat processing: {e}")
        return jsonify({"error": "Failed to get an answer from the AI."}), 500

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    app.run(debug=True, port=5001)