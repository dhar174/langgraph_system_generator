import json

with open('/tmp/all_issues_only.json', 'r') as f:
    issues = json.load(f)

# Sort issues by number (ascending)
issues.sort(key=lambda x: x['number'])

# Exclude 4-10
filtered_issues = [i for i in issues if i['number'] not in range(4, 11)]

scored_issues = []
for issue in filtered_issues:
    score = 0
    text = (issue['title'] or '') + " " + (issue['body'] or '')
    text = text.lower()

    if 'optional' in text: score += 5
    if 'refactor' in text: score += 3
    if 'integration' in text: score += 3
    if 'ui' in text or 'frontend' in text: score += 4
    if 'deployment' in text or 'docker' in text: score += 4
    if 'documentation' in text: score += 2
    if 'tests' in text: score += 2

    score -= issue['comments']

    scored_issues.append((score, issue))

scored_issues.sort(key=lambda x: x[0], reverse=True)
# The first 20 were picked last time (indices 0 to 19). We want the next 40 (indices 20 to 59).
next_40 = [item[1] for item in scored_issues[20:60]]

with open('/tmp/next_40_issues.json', 'w') as f:
    json.dump(next_40, f, indent=2)

print(f"Selected {len(next_40)} next issues.")
for i in next_40:
    print(f"#{i['number']}: {i['title']}")
