"""Source tracking must preserve detection input and expose honest coordinates."""
from pathlib import Path

import pytest

from edgar.documents import ParserConfig
from edgar.documents.agents import detect_filing_agent
from edgar.documents.parser import HTMLParser
from edgar.documents.document import Section
from edgar.documents.nodes import SectionNode
from edgar.documents.extractors.index_section_detector import _make_text_extractor


def parse(html, track=True):
    return HTMLParser(ParserConfig(form='10-K', track_source=track, extract_xbrl=False)).parse(html)


def test_tracking_is_opt_in_and_keeps_the_original_agent_signature():
    html = '<!-- Workiva --><body><p>Cover</p><h2>Item 1. Business</h2><p>Operations</p></body>'
    normal, tracked = parse(html, False), parse(html)
    assert normal.source_tree is None
    assert tracked.metadata.original_html == html
    assert detect_filing_agent(tracked.metadata.original_html) == 'Workiva'
    assert set(normal.sections) == set(tracked.sections)
    assert normal.to_markdown() == tracked.to_markdown()
    assert 'data-max-source-position' not in tracked.metadata.original_html


def test_inline_body_headings_never_promote_to_the_document_root():
    document = parse('<html><body><font>Item 1. Business</font><br>OPERATIONS<br>'
                     '<font>Item 2. Properties</font><br>BUILDINGS</body></html>')
    nodes = [n for n in document.root.walk() if n.metadata.get('source_position') is not None
             and document._source_elements[n.metadata['source_position']].tag == 'font']
    assert len(nodes) == 2
    starts = [document.source_position(n) for n in nodes]
    assert len(set(starts)) == 2
    assert all(document._source_elements[p].tag == 'font' for p in starts)


def test_both_sides_of_a_pattern_boundary_use_the_heading_block():
    document = parse('<body><h2>Item 1. Business</h2><p>OPERATIONS</p>'
                     '<p><b>Item 2.</b> <span>Properties</span></p><p>BUILDINGS</p></body>')
    sections = {s.item: s for s in document.sections.values()}
    assert sections['1'].source_end == sections['2'].source_start
    assert document._source_elements[sections['2'].source_start].tag == 'p'


def test_empty_toc_anchors_survive_tracking_without_changing_text():
    html = '<body><div id="item1"></div><p>Business</p></body>'
    normal, tracked = parse(html, False), parse(html)
    assert tracked.source_tree.xpath('//*[@id="item1"]')
    assert normal.to_markdown() == tracked.to_markdown()


def test_index_sections_render_the_page_slice_with_table_structure():
    class Index:
        calls = 0
        def extract_item_content(self, item):
            assert item == '8'
            self.calls += 1
            return '<h2>Financial Statements</h2><table><tr><td>Revenue</td><td>123</td></tr></table>'
    index = Index()
    section = Section(name='part_ii_item_8', title='Item 8', node=SectionNode(),
                      detection_method='index', _text_extractor=_make_text_extractor(index, '8'))
    markdown = section.markdown()
    assert '| Revenue | 123 |' in markdown
    assert section.markdown() == markdown
    assert index.calls == 1
    assert section.source_start is None and section.source_end is None


def test_missing_index_page_content_is_explicitly_empty():
    class Index:
        def extract_item_content(self, item):
            return ''
    section = Section(name='part_ii_item_8', title='Item 8', node=SectionNode(),
                      detection_method='index', _text_extractor=_make_text_extractor(Index(), '8'))
    assert section.markdown() == ''


@pytest.mark.parametrize('symbol,filename', [
    ('cat','cat-10-k-2025-02-14.html'),
    ('pg','pg-10-k-2025-08-04.html'),
    ('ma','ma-10-k-2025-02-12.html'),
])
def test_coarse_toc_and_pattern_detection_agree_on_item_identity(symbol, filename):
    html = (Path(__file__).parent / 'fixtures/html' / symbol / '10k' / filename).read_text()
    document = parse(html)
    sections = list(document.sections.values())
    for item, part in [('5','II'), ('10','III'), ('15','IV')]:
        matches = [s for s in sections if s.item == item]
        assert len(matches) == 1
        assert matches[0].part == part
        assert matches[0].markdown().strip()
    assert detect_filing_agent(document.metadata.original_html) == detect_filing_agent(html) == 'Workiva'


@pytest.mark.parametrize("failure", ["raises", "empty"])
def test_index_markdown_failure_falls_back_to_text(failure):
    def extract(name, **kwargs):
        if kwargs.get('format') == 'markdown':
            if failure == 'raises':
                raise ValueError('renderer failed')
            return ''
        return 'Revenue 123. Preserved plain text.'
    section = Section(name='part_ii_item_8', title='Item 8', node=SectionNode(),
                      detection_method='index', _text_extractor=extract)
    assert section.markdown() == 'Revenue 123. Preserved plain text.'


@pytest.mark.parametrize('tag', ['td', 'th', 'tr', 'li', 'dt', 'dd'])
def test_inline_heading_stops_at_its_cell_or_list_item(tag):
    from types import SimpleNamespace
    from lxml import html
    from edgar.documents.document import Document
    # Feed the retained DOM directly: the source-position contract must work
    # independently of which tags the builder currently happens to retain.
    tree = html.fromstring(f'<div><p>PREVIOUS ITEM</p><{tag}><span>Next heading</span></{tag}></div>')
    elements = list(tree.iter())
    document = Document(root=SectionNode(), source_tree=tree, _source_elements=elements,
                        _source_order={id(element): i for i, element in enumerate(elements)})
    position = next(i for i, element in enumerate(elements) if element.tag == 'span')
    result = document.source_position(SimpleNamespace(metadata={'source_position': position}))
    assert elements[result].tag == tag


def test_inline_heading_cannot_climb_past_previous_item_content():
    document = parse('<body><div><font>Item 1. Business</font><p>FIRST ITEM CONTENT</p>'
                     '<font>Item 2. Properties</font><p>SECOND ITEM CONTENT</p></div></body>')
    nodes = [n for n in document.root.walk() if n.metadata.get('source_position') is not None
             and document._source_elements[n.metadata['source_position']].tag == 'font']
    assert len(nodes) == 2
    positions = [document.source_position(node) for node in nodes]
    first_body = next(i for i, element in enumerate(document._source_elements)
                      if element.tag == 'p' and element.text == 'FIRST ITEM CONTENT')
    assert positions[0] < first_body < positions[1]
