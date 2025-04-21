import json
import http.client
from config import SERPER_API_KEY

def web_search(query):
    """
    Perform a web search using the Serper API and return the results.
    """
    try:
        conn = http.client.HTTPSConnection("google.serper.dev")
        payload = json.dumps({
            "q": query
        })
        headers = {
            'X-API-KEY': SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
        conn.request("POST", "/search", payload, headers)
        res = conn.getresponse()
        data = res.read()
        search_results = json.loads(data.decode("utf-8"))
        
        # Extract and format the search results
        formatted_results = []
        
        # Extract organic search results
        if "organic" in search_results:
            for i, result in enumerate(search_results["organic"][:3]):  # Get top 3 results
                title = result.get("title", "")
                snippet = result.get("snippet", "")
                formatted_results.append(f"{i+1}. {title}: {snippet}")
        
        # Extract knowledge graph if available
        if "knowledgeGraph" in search_results:
            kg = search_results["knowledgeGraph"]
            title = kg.get("title", "")
            description = kg.get("description", "")
            if title and description:
                formatted_results.append(f"Knowledge Graph: {title} - {description}")
        
        # Extract answer box if available
        if "answerBox" in search_results:
            answer = search_results["answerBox"]
            title = answer.get("title", "")
            answer_text = answer.get("answer", "")
            snippet = answer.get("snippet", "")
            if answer_text:
                formatted_results.append(f"Answer: {answer_text}")
            elif title and snippet:
                formatted_results.append(f"Featured Snippet: {title} - {snippet}")
        
        return "\n".join(formatted_results)
    
    except Exception as e:
        print(f"Error during web search: {e}")
        return f"Error performing web search: {str(e)}"