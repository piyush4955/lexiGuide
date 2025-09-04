# backend/app.py
import os
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import google.generativeai as genai
import PyPDF2

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
app = Flask(__name__, static_folder='../frontend', static_url_path='/')

def extract_text_from_pdf(file_stream):
    try:
        pdf_reader = PyPDF2.PdfReader(file_stream)
        text = "".join(page.extract_text() for page in pdf_reader.pages)
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return None

def get_gemini_response(prompt):
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return f"Sorry, there was an error with the AI model: {e}"

# --- MULTILINGUAL PROMPT TEMPLATES ---

# Note the new {language} placeholder in every prompt.
RENTAL_PROMPT = """
Analyze the following rental agreement from India. Provide the entire response in the {language} language.

**Part 1: Summary**
Extract these key points:
- Parties Involved
- Property Address
- Key Financials (Rent, Security Deposit in INR)
- Duration (Start date, end date)
- Notice Period

**Part 2: Action Checklist**
Generate a short, bulleted checklist of 3-4 practical action items for the tenant.

DOCUMENT TEXT: "{document_text}"
RESPONSE in {language}:
"""

LOAN_PROMPT = """
Analyze the following loan contract from India. Provide the entire response in the {language} language.

**Part 1: Summary**
Extract these key financial points:
- Parties Involved
- Loan Principal Amount (in INR)
- Interest Rate
- Loan Term/Tenure
- EMI/Payment Structure
- Collateral

**Part 2: Action Checklist**
Generate a short, bulleted checklist of 3-4 practical action items for the borrower.

DOCUMENT TEXT: "{document_text}"
RESPONSE in {language}:
"""

TOS_PROMPT = """
Analyze the following Terms of Service document. Provide the entire response in the {language} language.

**Part 1: Summary**
Focus on these critical areas for a user in India:
- Data Privacy
- User Obligations (what a user cannot do)
- Termination Clause
- Limitation of Liability

**Part 2: Action Checklist**
Generate a short, bulleted checklist of 3-4 practical action items for the user.

DOCUMENT TEXT: "{document_text}"
RESPONSE in {language}:
"""

RISK_ANALYSIS_PROMPT = """
You are a paralegal AI specializing in Indian contracts. Analyze the following legal document.
Identify potential risks or "gotcha" clauses for the primary user.
List each potential risk with a simple explanation of why it's a concern. If no significant risks are found, state that the document appears standard.
Provide the entire response in the {language} language.

DOCUMENT TEXT: "{document_text}"
RISK ANALYSIS in {language}:
"""

QA_PROMPT = """
Based ONLY on the provided document text, answer the user's question.
Provide the answer in the {language} language.
If the answer is not in the text, state clearly (in {language}): "The answer to that question could not be found in the document."

DOCUMENT TEXT: "{document_text}"
QUESTION: "{question}"
ANSWER in {language}:
"""

# --- FLASK ROUTES ---

@app.route('/analyze', methods=['POST'])
def analyze_document():
    if 'document' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['document']
    doc_type = request.form.get('doc_type')
    language = request.form.get('language', 'English') # Default to English if not provided

    if not file or not doc_type:
        return jsonify({"error": "Missing file or document type"}), 400

    try:
        document_text = extract_text_from_pdf(file.stream)
        if not document_text or len(document_text.strip()) < 50:
             return jsonify({"error": "Could not extract sufficient readable text."}), 400

        # Select the correct base prompt
        if "Loan Contract" == doc_type:
            summary_prompt_template = LOAN_PROMPT
        elif "Terms of Service" == doc_type:
            summary_prompt_template = TOS_PROMPT
        else:
            summary_prompt_template = RENTAL_PROMPT
        
        # Format prompts with the selected language
        summary_and_checklist_prompt = summary_prompt_template.format(document_text=document_text, language=language)
        summary_and_checklist = get_gemini_response(summary_and_checklist_prompt)
        
        risk_analysis_prompt = RISK_ANALYSIS_PROMPT.format(document_text=document_text, language=language)
        risk_analysis = get_gemini_response(risk_analysis_prompt)
        
        return jsonify({
            "summary_and_checklist": summary_and_checklist, 
            "risk_analysis": risk_analysis,
            "full_text": document_text,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/ask', methods=['POST'])
def ask_question():
    data = request.get_json()
    document_text = data.get('full_text')
    question = data.get('question')
    language = data.get('language', 'English') # Default to English

    if not all([document_text, question]):
        return jsonify({"error": "Missing document text or question"}), 400
        
    # Format the Q&A prompt with the selected language
    prompt = QA_PROMPT.format(document_text=document_text, question=question, language=language)
    answer = get_gemini_response(prompt)
    return jsonify({"answer": answer})

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)