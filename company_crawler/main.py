from physical_intelligence.main import run as run_pi
from skild_ai.main import run as run_skild
from dyna.main import run as run_dyna

def crawl_company():
    results = []
    purpose = input("What data do you want to crawl? (blog/career/all)")
    results.append(run_pi(purpose))
    results.append(run_skild(purpose))
    results.append(run_dyna(purpose))
    return results

if __name__ == "__main__":
    print(crawl_company())