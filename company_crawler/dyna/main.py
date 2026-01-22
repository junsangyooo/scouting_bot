from dyna.blog_crawler import blog_crawler
from dyna.blog_compare import blog_compare
from dyna.position_crawler import position_crawler
from dyna.position_compare import position_compare

def run(purpose):
    # Crawl and Compare Researches
    if purpose == "blog" or purpose == "all":
        blogs = blog_crawler()
        blog_result = blog_compare(blogs)
        if purpose == "blog":
            return {
                "company": "DYNA",
                "blog": blog_result
            }

    # Crawl and Compare Positions
    if purpose == "career" or purpose == "all":
        positions = position_crawler()
        position_result = position_compare(positions)
        if purpose == "career":
            return {
                "company": "DYNA",
                "position": position_result
            }

    return {
        "company": "DYNA",
        "blog": blog_result,
        "position": position_result
    }

if __name__ == "__main__":
    print(run())