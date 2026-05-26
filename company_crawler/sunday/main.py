from sunday.blog_crawler import blog_crawler
from sunday.blog_compare import blog_compare
from sunday.position_crawler import position_crawler
from sunday.position_compare import position_compare


def run(purpose):
    if purpose == "all":
        blogs = blog_crawler()
        research_result = blog_compare(blogs)

        positions = position_crawler()
        position_result = position_compare(positions)

        return {
            "company": "Sunday Robotics",
            "research": research_result,
            "position": position_result,
        }

    if purpose == "blog":
        blogs = blog_crawler()
        research_result = blog_compare(blogs)

        return {
            "company": "Sunday Robotics",
            "research": research_result,
        }

    if purpose == "career":
        positions = position_crawler()
        position_result = position_compare(positions)

        return {
            "company": "Sunday Robotics",
            "position": position_result,
        }


if __name__ == "__main__":
    print(run("all"))
