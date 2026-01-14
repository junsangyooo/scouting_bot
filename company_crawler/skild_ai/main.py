from skild_ai.blog_crawler import blog_crawler
from skild_ai.blog_compare import blog_compare
from skild_ai.position_crawler import position_crawler
from skild_ai.position_compare import position_compare

def run():
    # Crawl and Compare Researches
    blogs = blog_crawler()
    blog_result = blog_compare(blogs)

    # Crawl and Compare Positions
    positions = position_crawler()
    position_result = position_compare(positions)
    return {
        "company": "Skild AI",
        "blog": blog_result,
        "position": position_result
    }

if __name__ == "__main__":
    print(run())