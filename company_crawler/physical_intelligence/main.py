from physical_intelligence.blog_crawler import blog_crawler
from physical_intelligence.blog_compare import blog_compare
from physical_intelligence.position_crawler import position_crawler
from physical_intelligence.position_compare import position_compare

def run(purpose):
    if purpose == "all":
        # Crawl and Compare Researches
        blogs = blog_crawler()
        research_result = blog_compare(blogs)

        # Crawl and Compare Positions
        positions = position_crawler()
        position_result = position_compare(positions)

        return {
            "company": "Physical Intelligence",
            "research": research_result,
            "position": position_result
        }

    # Crawl and Compare Researches
    if purpose == "blog":
        blogs = blog_crawler()
        research_result = blog_compare(blogs)

        return {
            "company": "Physical Intelligence",
            "research": research_result
        }

    # Crawl and Compare Positions
    if purpose == "career":
        positions = position_crawler()
        position_result = position_compare(positions)

        return {
            "company": "Physical Intelligence",
            "position": position_result
        }

if __name__ == "__main__":
    print(run("all"))