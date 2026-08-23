"""Filing identifiers survive text cleanup; numbered notes are not SEC Items."""
import pytest
from lxml import html

pytestmark = pytest.mark.fast
from edgar.documents import ParserConfig
from edgar.documents.parser import HTMLParser
from edgar.documents.processors.preprocessor import HTMLPreprocessor
from edgar.documents.utils.toc_analyzer import TOCAnalyzer


@pytest.mark.parametrize('track', [False, True])
def test_text_normalization_keeps_attribute_values(track):
    markup = ('<html><body><h2 id="Item1.Business" data-value="A  &nbsp; B > C.D">'
              'Item 1.Business</h2><a href="#Item1.Business" name="legacy  A.B">Business</a>'
              '<p>First.Second , third.</p></body></html>')
    before = html.document_fromstring(markup)
    processed = HTMLPreprocessor(ParserConfig(track_source=track)).process(markup)
    after = html.document_fromstring(processed)
    for selector in ('.//h2','.//a'):
        assert before.find(selector).attrib == after.find(selector).attrib
    assert 'First. Second, third.' in after.text_content()


def test_anchor_positions_resolve_in_both_tracking_modes():
    markup = ('<html><body><table>'
              '<tr><td><a href="#Item1.Business">Item 1. Business</a></td></tr>'
              '<tr><td><a href="#Item2.Properties">Item 2. Properties</a></td></tr>'
              '</table><h2 id="Item1.Business">Item 1. Business</h2><p>Operations</p>'
              '<h2 id="Item2.Properties">Item 2. Properties</h2><p>Buildings</p></body></html>')
    normal = HTMLParser(ParserConfig(form='10-K',extract_xbrl=False)).parse(markup)
    tracked = HTMLParser(ParserConfig(form='10-K',extract_xbrl=False,track_source=True)).parse(markup)
    assert set(normal.sections) == set(tracked.sections)
    assert normal.to_markdown() == tracked.to_markdown()
    for bound in tracked._get_section_extractor().section_boundaries.values():
        assert tracked.source_tree.xpath('//*[@id=$anchor]',anchor=bound.anchor_id)


def test_note_index_heading_applies_after_introductory_rows():
    intro = '<tr><td>Financial overview</td></tr>'*5
    markup = ('<html><body><table>'+intro+'<tr><td>Notes on financial statements</td></tr>'
              '<tr><td>1.</td><td>Accounting policies</td><td><a href="#n1">160</a></td></tr>'
              '<tr><td>3.</td><td>Business combinations</td><td><a href="#n3">182</a></td></tr>'
              '</table><h2 id="n1">1. Accounting policies</h2><h2 id="n3">3. Business combinations</h2></body></html>')
    assert TOCAnalyzer(form='20-F').analyze_toc_structure(markup) == {}


def test_page_footer_number_does_not_label_a_prose_reference():
    tree = html.fromstring('<table><tr><td>2</td><td>Annual report</td>'
                           '<td>See glossary on page <a href="#glossary">375</a></td></tr></table>')
    assert TOCAnalyzer(form='20-F')._extract_preceding_item_label(tree.find('.//a')) == ''
    # A number column in a real bare-number Item index remains valid.
    tree = html.fromstring('<table><tr><td>1</td><td><a href="#business">Business</a></td></tr></table>')
    assert TOCAnalyzer(form='10-K')._extract_preceding_item_label(tree.find('.//a')) == 'Item 1'


@pytest.mark.parametrize('prefix,expected', [('Also see ', False), ('Please refer to ', False), ('Item 3. ', True), ('', True)])
def test_inline_heading_keeps_its_reference_context(prefix, expected):
    from edgar.documents.document import Document
    from edgar.documents.nodes import SectionNode, ParagraphNode, HeadingNode, TextNode
    from edgar.documents.extractors.pattern_section_extractor import SectionExtractor
    root = SectionNode()
    paragraph = ParagraphNode()
    root.add_child(paragraph)
    paragraph.add_child(TextNode(content=prefix))
    heading = HeadingNode(content='Risk factors')
    paragraph.add_child(heading)
    paragraph.add_child(TextNode(content=' on page 67 for further information.'))
    document = Document(root=root)
    candidates = SectionExtractor('20-F')._find_section_headers(document)
    assert any(node is heading for node, _, _ in candidates) == expected



def test_linked_notes_entry_does_not_change_the_item_index_scope():
    tree = html.fromstring('<table><tr><td>Item</td><td>Title</td><td>Page</td></tr>'
                          '<tr><td></td><td><a href="#notes">Notes to Consolidated Financial Statements</a></td></tr>'
                          '<tr><td>10.</td><td><a href="#directors">Directors</a></td></tr></table>')
    link = tree.xpath('.//a[@href="#directors"]')[0]
    assert TOCAnalyzer(form='10-K')._extract_preceding_item_label(link) == 'Item 10'


def test_item_title_with_a_reference_is_not_a_page_footer():
    tree = html.fromstring('<table><tr><td>10.</td>'
                          '<td><a href="#directors">Directors: refer to proxy statement</a></td></tr></table>')
    assert TOCAnalyzer(form='10-K')._extract_preceding_item_label(tree.find('.//a')) == 'Item 10'



def test_note_column_on_the_first_row_is_not_an_item_number():
    tree = html.fromstring('<table><tr><td>Note</td><td>1</td><td>Basis of presentation</td>'
                          '<td><a href="#note1">11</a></td></tr></table>')
    assert TOCAnalyzer(form='10-Q')._extract_preceding_item_label(tree.find('.//a')) == ''



@pytest.mark.parametrize('subrow', ['Notes to Consolidated Financial Statements', 'Exhibits'])
@pytest.mark.parametrize('track', [False, True])
def test_unlinked_toc_subrows_preserve_nonstandard_item_titles(subrow, track):
    rows = '<tr><td>Item</td><td>Title</td><td>Page</td></tr>'
    rows += '<tr><td>8</td><td>Financial statements</td><td><a href="#i8">90</a></td></tr>'
    rows += f'<tr><td></td><td>{subrow}</td><td>91</td></tr>'
    rows += ''.join(f'<tr><td>{n}</td><td>Disclosure category {n}</td>'
                    f'<td><a href="#i{n}">{100+n}</a></td></tr>' for n in range(9, 16))
    source = '<html><body><h1>Annual report</h1><table>' + rows + '</table>'
    source += ''.join(f'<h2 id="i{n}">Disclosure category {n}</h2>'
                      f'<p>UNIQUE-DISCLOSURE-{n}. This passage belongs to this section.</p>'
                      for n in range(8, 16))
    source += '</body></html>'
    document = HTMLParser(ParserConfig(form='10-K', extract_xbrl=False, track_source=track)).parse(source)
    items = {section.item: section for section in document.sections.values()}
    assert set(items) == {str(n) for n in range(8, 16)}
    for n in range(8, 16):
        assert f'UNIQUE-DISCLOSURE-{n}' in items[str(n)].text()


def test_numbered_exhibits_title_is_not_an_exhibit_number_column():
    tree = html.fromstring('<table><tr><td>15</td><td>Exhibits</td>'
                          '<td><a href="#item15">150</a></td></tr></table>')
    assert TOCAnalyzer(form='10-K')._extract_preceding_item_label(tree.find('.//a')) == 'Item 15'
