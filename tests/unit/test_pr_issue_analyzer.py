"""Tests for PR issue relevance analysis utilities."""

from langgraph_system_generator.analysis.pr_issue_analyzer import (
    Issue,
    analyze_pr_issues,
    score_issue,
)


def test_score_issue_prioritizes_title_matches():
    issue = Issue(id=1, title="Fix PR relevance sorting", body="Need to sort issues")
    keywords = ["relevance", "sort"]

    score = score_issue(issue, keywords)

    # Title match gets higher weight (3) vs body (1)
    assert score >= 3, "Title match should contribute higher weight"


def test_analyze_pr_issues_sorts_by_score_desc():
    issues = [
        Issue(id=1, title="Unrelated change", body="minor update"),
        Issue(id=2, title="Improve PR issue relevance", body="sort open PR issues"),
        Issue(id=3, title="Add docs", body="update readme"),
    ]
    keywords = ["PR", "relevance"]

    sorted_issues = analyze_pr_issues(issues, keywords)

    assert sorted_issues[0].id == 2, "Issue with strongest match should come first"
    assert sorted_issues[-1].id == 1, "Unrelated issue should rank last"

