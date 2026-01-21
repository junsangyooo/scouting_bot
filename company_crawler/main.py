from physical_intelligence.main import run as run_pi
from skild_ai.main import run as run_skild
from dyna.main import run as run_dyna

COMPANIES = {
    "pi": ("Physical Intelligence", run_pi),
    "skild": ("Skild AI", run_skild),
    "dyna": ("DYNA", run_dyna),
}

PURPOSES = ["blog", "career", "all"]


def crawl_company():
    # Step 1: Select company
    print("\n=== Company Crawler ===\n")
    print("Select company to crawl:")
    print("  - pi    : Physical Intelligence")
    print("  - skild : Skild AI")
    print("  - dyna  : DYNA")
    print("  - all   : All companies")

    company = input("\nCompany (pi/skild/dyna/all): ").strip().lower()

    if company not in ["pi", "skild", "dyna", "all"]:
        print(f"[ERROR] Invalid company: {company}")
        return None

    # Step 2: Select purpose
    print("\nSelect data to crawl:")
    print("  - blog   : Blog/Research posts")
    print("  - career : Job positions")
    print("  - all    : Both blog and career")

    purpose = input("\nPurpose (blog/career/all): ").strip().lower()

    if purpose not in PURPOSES:
        print(f"[ERROR] Invalid purpose: {purpose}")
        return None

    # Step 3: Execute crawling
    results = []

    if company == "all":
        for key, (name, runner) in COMPANIES.items():
            print(f"\n[INFO] Crawling {name}...")
            try:
                result = runner(purpose)
                results.append(result)
                print(f"[INFO] {name} completed")
            except Exception as e:
                print(f"[ERROR] {name} failed: {e}")
                results.append({"company": name, "error": str(e)})
    else:
        name, runner = COMPANIES[company]
        print(f"\n[INFO] Crawling {name}...")
        try:
            result = runner(purpose)
            results.append(result)
            print(f"[INFO] {name} completed")
        except Exception as e:
            print(f"[ERROR] {name} failed: {e}")
            results.append({"company": name, "error": str(e)})

    return results


def print_results(results):
    if not results:
        return

    print("\n" + "=" * 50)
    print("CRAWL RESULTS")
    print("=" * 50)

    for result in results:
        if not result:
            continue

        company = result.get("company", "Unknown")
        print(f"\n[{company}]")

        if "error" in result:
            print(f"  Error: {result['error']}")
            continue

        # Blog results
        if "blog" in result or "research" in result:
            blog_data = result.get("blog") or result.get("research", {})
            status = blog_data.get("status", "N/A")
            print(f"  Blog: {status}")
            if status == "updated":
                added = blog_data.get("added", [])
                removed = blog_data.get("removed", [])
                if added:
                    print(f"    + Added: {len(added)} posts")
                if removed:
                    print(f"    - Removed: {len(removed)} posts")

        # Position results
        if "position" in result:
            pos_data = result.get("position", {})
            status = pos_data.get("status", "N/A")
            print(f"  Career: {status}")
            if status == "updated":
                added = pos_data.get("added", [])
                removed = pos_data.get("removed", [])
                updated = pos_data.get("updated", [])
                if added:
                    print(f"    + Added: {len(added)} positions")
                if removed:
                    print(f"    - Removed: {len(removed)} positions")
                if updated:
                    print(f"    ~ Updated: {len(updated)} positions")

        # Team results (PI only)
        if "team" in result:
            team_data = result.get("team", {})
            status = team_data.get("status", "N/A")
            print(f"  Team: {status}")


if __name__ == "__main__":
    results = crawl_company()
    print_results(results)