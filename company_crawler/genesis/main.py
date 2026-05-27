from genesis.blog_crawler import blog_crawler
from genesis.blog_compare import blog_compare
from genesis.position_crawler import position_crawler
from genesis.position_compare import position_compare


def run(purpose):
    if purpose == "all":
        blogs = blog_crawler()
        blog_result = blog_compare(blogs)

        positions = position_crawler()
        position_result = position_compare(positions)

        return {
            "company": "Genesis AI",
            "blog": blog_result,
            "position": position_result,
        }

    if purpose == "blog":
        blogs = blog_crawler()
        blog_result = blog_compare(blogs)

        return {
            "company": "Genesis AI",
            "blog": blog_result,
        }

    if purpose == "career":
        positions = position_crawler()
        position_result = position_compare(positions)

        return {
            "company": "Genesis AI",
            "position": position_result,
        }


if __name__ == "__main__":
    print(run("all"))
