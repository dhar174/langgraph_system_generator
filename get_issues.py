import json
import urllib.request
import sys

issues = []
page = 1
while True:
    url = f"https://api.github.com/repos/dhar174/langgraph_system_generator/issues?state=closed&per_page=100&page={page}"
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if not data:
                break
            for item in data:
                if 'pull_request' not in item:
                    issues.append({
                        'number': item['number'],
                        'title': item['title'],
                        'body': item['body'],
                        'comments': item['comments']
                    })
            page += 1
    except Exception as e:
        print(f"Error: {e}")
        break

with open('/tmp/all_issues_only.json', 'w') as f:
    json.dump(issues, f, indent=2)

print(f"Total issues found: {len(issues)}")
