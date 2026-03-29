import requests
from bs4 import BeautifulSoup

def getCurrentDomainName(website_type="hollywood"):
    base_url = "https://modlist.in/"
    request_url = base_url + f"?type={website_type}"

    response = requests.get(request_url).text
    soup = BeautifulSoup(response, "html.parser")
    redirect_text = soup.h4.text
    currentDomain = redirect_text.strip("Redirecting to ")
    
    return currentDomain