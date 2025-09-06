import os
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import google.generativeai as genai
import datetime

# --- NEW: Replaced PyPDF2 with the more robust pdfplumber library ---
import pdfplumber

# Firebase Admin imports
import firebase_admin
from firebase_admin import credentials, auth, firestore

# --- INITIALIZATION ---
load_dotenv()

# Initialize Firebase Admin SDK
# Make sure 'serviceAccountKey.json' is in your 'backend' folder
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Initialize Gemini AI
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Initialize Flask App
app = Flask(__name__, static_folder='../frontend', static_url_path='/')


# --- HELPER FUNCTIONS ---

# --- UPDATED: This function now uses pdfplumber for better text extraction ---
def extract_text_from_pdf(file_stream):
    """Extracts text from a document using the pdfplumber library."""
    text = ""
    try:
        # pdfplumber.open() can directly handle the file stream from Flask
        with pdfplumber.open(file_stream) as pdf:
            # Loop through each page of the PDF
            for page in pdf.pages:
                # Extract text from the page
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"  # Add text and a newline for separation
        return text
    except Exception as e:
        print(f"Error reading PDF with pdfplumber: {e}")
        return None

def get_gemini_response(prompt):
    """Sends a prompt to the Gemini API and returns the text response."""
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return f"Sorry, there was an error with the AI model: {e}"


# --- MULTILINGUAL PROMPT TEMPLATES (Unchanged) ---

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
List each potential risk with a simple explanation of why it's a concern. If no significant risks are found, state that the document appears to be standard.
Provide the entire response in the {language} language.

DOCUMENT TEXT: "{document_text}"
RISK ANALYSIS in {language}:
"""

# --- FLASK ROUTES ---

@app.route('/analyze', methods=['POST'])
def analyze_document():
    # 1. Authenticate the user
    try:
        id_token = request.headers['Authorization'].split(' ').pop()
        decoded_token = auth.verify_id_token(id_token)
        uid = decoded_token['uid']
    except Exception as e:
        print(e)
        return jsonify({"error": "Unauthorized request. Please log in."}), 401

    # 2. Get the uploaded file and form data
    if 'document' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['document']
    doc_type = request.form.get('doc_type')
    language = request.form.get('language', 'English')
    filename = request.form.get('filename', 'Untitled Document')

    if not file or not doc_type:
        return jsonify({"error": "Missing file or document type"}), 400

    try:
        # 3. Extract text using our new, improved function
        document_text = extract_text_from_pdf(file.stream)
        
        # Check if the extraction was successful
        if not document_text or len(document_text.strip()) < 50:
             return jsonify({"error": "Could not extract sufficient readable text from this PDF. The file might be corrupted or have an unusual format."}), 400

        # 4. Select the correct prompt based on user's choice
        if "Loan Contract" == doc_type:
            summary_prompt_template = LOAN_PROMPT
        elif "Terms of Service" == doc_type:
            summary_prompt_template = TOS_PROMPT
        else:
            summary_prompt_template = RENTAL_PROMPT
        
        # 5. Get Summary & Checklist from AI
        summary_and_checklist_prompt = summary_prompt_template.format(document_text=document_text, language=language)
        summary_and_checklist = get_gemini_response(summary_and_checklist_prompt)
        
        # 6. Get Risk Analysis from AI
        risk_analysis_prompt = RISK_ANALYSIS_PROMPT.format(document_text=document_text, language=language)
        risk_analysis = get_gemini_response(risk_analysis_prompt)
        
        # 7. Save results to Firestore
        doc_ref = db.collection('users').document(uid).collection('documents').document()
        doc_ref.set({
            'filename': filename,
            'doc_type': doc_type,
            'language': language,
            'summary_and_checklist': summary_and_checklist,
            'risk_analysis': risk_analysis,
            'analyzedAt': datetime.datetime.now(tz=datetime.timezone.utc),
        })

        # 8. Send results back to the frontend
        return jsonify({
            "summary_and_checklist": summary_and_checklist, 
            "risk_analysis": risk_analysis,
        })

    except Exception as e:
        print(f"An error occurred in /analyze route: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500

# Route to serve the main HTML file
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

# Main entry point to run the Flask app
if __name__ == '__main__':
    app.run(debug=True, port=5000)
