import os
import datetime
import uuid
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import google.generativeai as genai
import pdfplumber

# Firebase Admin imports
import firebase_admin
from firebase_admin import credentials, auth, firestore

# --- INITIALIZATION ---
load_dotenv()
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
app = Flask(__name__, static_folder='../frontend', static_url_path='/')

# --- HELPER FUNCTIONS ---
def extract_text_from_pdf(file_stream):
    text = ""
    try:
        with pdfplumber.open(file_stream) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF with pdfplumber: {e}")
        return None

def get_gemini_response(prompt):
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return f"Sorry, there was an error with the AI model: {e}"

# --- PROMPT TEMPLATES ---
RENTAL_PROMPT = """
Analyze the following rental agreement from India. Provide the entire response in the {language} language.
**Part 1: Summary**
Extract these key points:
- Parties Involved, Property Address, Key Financials (Rent, Security Deposit in INR), Duration (Start date, end date), Notice Period
**Part 2: Action Checklist**
Generate a short, bulleted checklist of 3-4 practical action items for the tenant.
DOCUMENT TEXT: "{document_text}"
RESPONSE in {language}:
"""
LOAN_PROMPT = """
Analyze the following loan contract from India. Provide the entire response in the {language} language.
**Part 1: Summary**
Extract these key financial points:
- Parties Involved, Loan Principal Amount (in INR), Interest Rate, Loan Term/Tenure, EMI/Payment Structure, Collateral
**Part 2: Action Checklist**
Generate a short, bulleted checklist of 3-4 practical action items for the borrower.
DOCUMENT TEXT: "{document_text}"
RESPONSE in {language}:
"""
TOS_PROMPT = """
Analyze the following Terms of Service document. Provide the entire response in the {language} language.
**Part 1: Summary**
Focus on these critical areas for a user in India:
- Data Privacy, User Obligations, Termination Clause, Limitation of Liability
**Part 2: Action Checklist**
Generate a short, bulleted checklist of 3-4 practical action items for the user.
DOCUMENT TEXT: "{document_text}"
RESPONSE in {language}:
"""
RISK_ANALYSIS_PROMPT = """
You are a paralegal AI specializing in Indian contracts. Analyze the following legal document.
Identify potential risks or "gotcha" clauses for the primary user.
List each potential risk with a simple explanation of why it's a concern. If no significant risks are found, state that the document appears to be standard.
Provide the entire response in the {language} language.
DOCUMENT TEXT: "{document_text}"
RISK ANALYSIS in {language}:
"""
EXPLAIN_TERM_PROMPT = """
You are an AI legal assistant. Explain the following legal term in one simple sentence, as you would to a non-lawyer in India.
Provide the entire response in the {language} language.
LEGAL TERM: "{term}"
SIMPLE EXPLANATION:
"""

# --- FLASK ROUTES ---

@app.route('/analyze', methods=['POST'])
def analyze_document():
    try:
        id_token = request.headers['Authorization'].split(' ').pop()
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
    except Exception as e:
        return jsonify({"error": "Unauthorized request. Please log in."}), 401
    if 'document' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['document']
    doc_type = request.form.get('doc_type')
    language = request.form.get('language', 'English')
    filename = request.form.get('filename', 'Untitled Document')
    tags_string = request.form.get('tags', '')
    tags_array = [tag.strip().lower() for tag in tags_string.split(',') if tag.strip()]
    try:
        document_text = extract_text_from_pdf(file.stream)
        if not document_text or len(document_text.strip()) < 50:
             return jsonify({"error": "Could not extract sufficient text from this PDF."}), 400
        if "Loan Contract" == doc_type: summary_prompt_template = LOAN_PROMPT
        elif "Terms of Service" == doc_type: summary_prompt_template = TOS_PROMPT
        else: summary_prompt_template = RENTAL_PROMPT
        summary_and_checklist_prompt = summary_prompt_template.format(document_text=document_text, language=language)
        summary_and_checklist = get_gemini_response(summary_and_checklist_prompt)
        risk_analysis_prompt = RISK_ANALYSIS_PROMPT.format(document_text=document_text, language=language)
        risk_analysis = get_gemini_response(risk_analysis_prompt)
        doc_ref = db.collection('users').document(uid).collection('documents').document()
        doc_ref.set({
            'filename': filename, 'doc_type': doc_type, 'language': language,
            'summary_and_checklist': summary_and_checklist, 'risk_analysis': risk_analysis,
            'tags': tags_array, 'analyzedAt': datetime.datetime.now(tz=datetime.timezone.utc),
        })
        return jsonify({
            "summary_and_checklist": summary_and_checklist, "risk_analysis": risk_analysis,
            "doc_id": doc_ref.id,
        })
    except Exception as e:
        print(f"An error occurred in /analyze: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500

@app.route('/create_share_link', methods=['POST'])
def create_share_link():
    try:
        id_token = request.headers['Authorization'].split(' ').pop()
        uid = auth.verify_id_token(id_token)['uid']
    except Exception: return jsonify({"error": "Unauthorized request."}), 401
    try:
        doc_id = request.get_json().get('doc_id')
        if not doc_id: return jsonify({"error": "Document ID is required."}), 400
        original_doc = db.collection('users').document(uid).collection('documents').document(doc_id).get()
        if not original_doc.exists: return jsonify({"error": "Original analysis not found."}), 404
        analysis_data = original_doc.to_dict()
        share_id = str(uuid.uuid4())
        share_ref = db.collection('shared_analyses').document(share_id)
        share_ref.set({
            'summary_and_checklist': analysis_data.get('summary_and_checklist'),
            'risk_analysis': analysis_data.get('risk_analysis'), 'filename': analysis_data.get('filename'),
            'doc_type': analysis_data.get('doc_type'), 'createdAt': datetime.datetime.now(tz=datetime.timezone.utc),
        })
        return jsonify({"share_id": share_id}), 200
    except Exception as e:
        print(f"Error creating share link: {e}")
        return jsonify({"error": "Could not create share link."}), 500

@app.route('/explain_term', methods=['POST'])
def explain_term():
    try:
        data = request.get_json()
        term = data.get('term')
        language = data.get('language', 'English')
        if not term: return jsonify({"error": "A term is required."}), 400
        prompt = EXPLAIN_TERM_PROMPT.format(term=term, language=language)
        explanation = get_gemini_response(prompt)
        return jsonify({"explanation": explanation}), 200
    except Exception as e:
        print(f"Error explaining term: {e}")
        return jsonify({"error": "Could not get an explanation."}), 500

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/share.html')
def serve_share_page():
    return send_from_directory(app.static_folder, 'share.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)

