from physical_intelligence.member_crawler import member_crawler
from physical_intelligence.member_compare import member_compare
from physical_intelligence.blog_crawler import blog_crawler
from physical_intelligence.blog_compare import blog_compare
from physical_intelligence.position_crawler import position_crawler
from physical_intelligence.position_compare import position_compare

def run():
    # Crawl and Compare Members
    members = member_crawler()
    member_result = member_compare(members)

    # Crawl and Compare Researches
    blogs = blog_crawler()
    research_result = blog_compare(blogs)

    # Crawl and Compare Positions
    positions = position_crawler()
    position_result = position_compare(positions)
    return {
        "company": "Physical Intelligence",
        "team": member_result,
        "research": research_result,
        "position": position_result
    }

if __name__ == "__main__":
    print(run())