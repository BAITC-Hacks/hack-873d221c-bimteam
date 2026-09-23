"""README не должен расходиться со сгенерированными примерами и путями."""
import json
import re

from app.config import ROOT


def test_readme_has_thirteen_sections_and_real_json_examples():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    assert len(re.findall(r'^# ', text, re.M)) == 1
    assert len(re.findall(r'^## ', text, re.M)) == 12
    cases = json.loads((ROOT / 'data/demo_queries.json').read_text(encoding='utf-8'))
    examples = [json.loads(block) for block in re.findall(r'```json\n(.*?)\n```', text, re.S)]
    assert len(examples) == 3
    for example, case in zip(examples, cases[2:]):
        response = case['response']
        assert example['status'] == response['status']
        assert example['message'] == response['message']
        assert len(example['cards']) == len(response['cards'])
        for card, actual in zip(example['cards'], response['cards']):
            assert card == {key: actual[key] for key in card}


def test_markdown_local_links_exist():
    for path in [ROOT / 'README.md', ROOT / 'docs/API.md', ROOT / 'docs/DEMO.md']:
        text = path.read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)]+)\)', text):
            if '://' not in target and not target.startswith('#'):
                assert (path.parent / target.split('#')[0]).exists(), (path.name, target)
