import requests
from bs4 import BeautifulSoup

def getCurrentDomainName(website_type="hollywood"):
    base_url = "https://modlist.in/"
    request_url = base_url + f"?type={website_type}"

    response = requests.get(request_url).text
    soup = BeautifulSoup(response, "html.parser")
    redirect_text = soup.h4.text
    # NB: str.strip() strips *characters*, not a prefix — it ate the
    # trailing "in" off "https://moviesmod.ai.in". removeprefix is exact.
    current_domain = redirect_text.removeprefix("Redirecting to ").strip()
    # Callers build URLs as f"{BASE}page/{i}" and match
    # f"{BASE}download...", so BASE must end in exactly one "/".
    return current_domain.rstrip("/") + "/"