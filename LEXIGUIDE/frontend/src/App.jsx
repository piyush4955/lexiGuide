import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import './App.css'; 

function App() {
  // States for main analysis
  const [docType, setDocType] = useState('rental');
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [expandedFlag, setExpandedFlag] = useState(null);
  const [originalText, setOriginalText] = useState(''); // <-- NEW: To store the document text

  // States for the new chat feature
  const [chatHistory, setChatHistory] = useState([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const chatEndRef = useRef(null);

  // Effect to scroll to the bottom of the chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatHistory]);

  const handleFileChange = (event) => {
    setFile(event.target.files[0]);
    setResult(null); 
    setError('');
    setExpandedFlag(null);
    setChatHistory([]); // Clear chat history
    setOriginalText(''); // Clear old text
  };
  
  const handleFlagClick = (index) => {
    setExpandedFlag(expandedFlag === index ? null : index);
  };

const handleSubmit = async () => {
  if (!file) {
    setError('Please select a file first.');
    return;
  }
  setIsLoading(true);
  setError('');
  setResult(null);
  setExpandedFlag(null);
  setChatHistory([]);
  setOriginalText('');

  const formData = new FormData();
  formData.append('file', file);
  formData.append('docType', docType);

  try {
    const response = await axios.post('http://localhost:5001/analyze', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });

    // The backend now sends an object with 'analysis' and 'documentText'
    setResult(response.data.analysis); 
    setOriginalText(response.data.documentText); // <-- CORRECTLY get the text from the backend

    // Initialize the chat with a welcome message
    setChatHistory([{ sender: 'ai', text: 'Analysis complete! Feel free to ask me any specific questions about this document below.' }]);
  } catch (err) {
    console.error("Analysis failed:", err);
    const errorMsg = err.response?.data?.error || 'Analysis failed. The server might be down or the document is corrupted.';
    setError(errorMsg);
  } finally {
    setIsLoading(false);
  }
};

  // --- NEW: Function to handle chat submission ---
  const handleChatSubmit = async (e) => {
    e.preventDefault(); // Prevent form from refreshing the page
    if (!chatInput.trim() || isChatLoading) return;

    const newChatHistory = [...chatHistory, { sender: 'user', text: chatInput }];
    setChatHistory(newChatHistory);
    setChatInput('');
    setIsChatLoading(true);

    try {
      const response = await axios.post('http://localhost:5001/chat', {
        documentText: originalText,
        question: chatInput,
      });
      setChatHistory([...newChatHistory, { sender: 'ai', text: response.data.answer }]);
    } catch (err) {
      console.error("Chat failed:", err);
      setChatHistory([...newChatHistory, { sender: 'ai', text: 'Sorry, I encountered an error. Please try again.' }]);
    } finally {
      setIsChatLoading(false);
    }
  };

  return (
    <div className="container">
      {/* ... header and upload section are the same ... */}
      <header><h1>LexiGuide AI</h1><p>Your personal guide to understanding complex legal documents.</p></header>
      <main>
        <div className="upload-section">
          <h2>1. Select Your Document Type</h2>
          <select value={docType} onChange={(e) => setDocType(e.target.value)} className="doc-select"><option value="rental">Rental Agreement</option><option value="loan">Loan Contract</option><option value="tos">Terms of Service</option></select>
          <h2>2. Upload Your Document</h2>
          <p>Upload your .pdf or .docx file to get started.</p>
          <input type="file" onChange={handleFileChange} accept=".pdf,.docx" className="file-input" />
          <button onClick={handleSubmit} disabled={isLoading} className="analyze-button">{isLoading ? 'Analyzing...' : 'Analyze Now'}</button>
        </div>

        {isLoading && <div className="loading-spinner"></div>}
        {error && <div className="error-message">{error}</div>}

        {result && (
          <div className="results-section">
            <h2>Analysis Complete</h2>
            {/* ... summary, details, and red flags cards are the same ... */}
            <div className="result-card summary"><h3>Summary</h3><p>{result.summary}</p></div>
            <div className="result-card details"><h3>Key Details</h3><table><tbody>{result.keyDetails.map((detail, index) => ( <tr key={index}> <td><strong>{detail.label}</strong></td> <td>{detail.value}</td> </tr> ))}</tbody></table></div>
            {result.redFlags && result.redFlags.length > 0 && (<div className="result-card red-flags"><h3>🚨 Red Flags (Click to expand)</h3>{result.redFlags.map((flag, index) => ( <div key={index} className={`flag severity-${flag.severity?.toLowerCase()}`} onClick={() => handleFlagClick(index)}><strong>{flag.clause}:</strong><p>{flag.concern}</p>{expandedFlag === index && (<div className="expanded-details"><h5>What to Look For:</h5><p>In your document, search for phrases like: <em>"{flag.whatToLookFor}"</em></p><h5>A Simple Question to Ask:</h5><p><em>"{flag.questionToAsk}"</em></p></div>)}</div>))}</div>)}
            
            {/* --- NEW CHAT INTERFACE --- */}
            <div className="result-card chat-section">
                <h3>Ask a Follow-up Question</h3>
                <div className="chat-history">
                  {chatHistory.map((msg, index) => (
                    <div key={index} className={`chat-message ${msg.sender}`}>
                      <p>{msg.text}</p>
                    </div>
                  ))}
                  {isChatLoading && <div className="chat-message ai"><div className="typing-indicator"></div></div>}
                  <div ref={chatEndRef} />
                </div>
                <form onSubmit={handleChatSubmit} className="chat-input-form">
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    placeholder="Ask anything about this document..."
                    disabled={isChatLoading}
                  />
                  <button type="submit" disabled={isChatLoading}>Send</button>
                </form>
            </div>
          </div>
        )}
      </main>
      <footer><p>Disclaimer: LexiGuide is an AI tool and does not provide legal advice. Always consult with a qualified professional.</p></footer>
    </div>
  );
}

export default App;