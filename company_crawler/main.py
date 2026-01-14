from physical_intelligence.main import run as run_pi
from skild_ai.main import run as run_skild

def crawl_company():
    results = []
    results.append(run_pi())
    results.append(run_skild())
    return results

if __name__ == "__main__":
    print(crawl_company())