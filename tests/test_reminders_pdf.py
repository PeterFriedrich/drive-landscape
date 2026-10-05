"""src/reminders_pdf.py grouping, on a made-up layout — no PDF, no PDF library."""
from src import reminders_pdf as rp

ROW = 31


def line(text, row, *, x0=43, size=10.7, bold=False, dy=0):
    top = 60 + row * ROW + dy
    return {"text": text, "bold_text": text if bold else "", "x0": x0, "top": top, "bottom": top + 12,
            "size": size, "bold": bold}


def marker(row, *, x0=24):
    top = 60 + row * ROW
    return {"x0": x0, "top": top, "bottom": top + 11}


def footer(n):
    return {"text": f"Errands {n}", "bold_text": "", "x0": 24, "top": 760, "bottom": 768, "size": 8.0, "bold": False}


TITLE = {"text": "Errands 5", "bold_text": "Errands", "x0": 24, "top": 20, "bottom": 40, "size": 19.2, "bold": False}

PAGES = [
    {
        "lines": [TITLE, line("buy stamps", 0), line("renew the library card before", 1),
                  line("it lapses", 1, dy=14), line("plan the trip", 2, bold=True),
                  line("book a train", 3, x0=62), line("Tomorrow", 3, x0=62, size=9.6, dy=14),
                  line("find the tent and check", 4), footer(1)],
        "markers": [marker(0), marker(1), marker(2), marker(3, x0=43), marker(4)],
    },
    {
        "lines": [line("the poles", 0), line("water the plants", 1), footer(2)],
        "markers": [marker(1)],
    },
]


def test_groups_items_wraps_subtasks_and_details():
    parsed = rp.group(PAGES)
    assert parsed["title"] == "Errands" and parsed["stated_count"] == 5
    assert [it["text"] for it in parsed["items"]] == [
        "buy stamps",
        "renew the library card before it lapses",
        "plan the trip",
        "book a train",
        "find the tent and check the poles",  # wrapped over a page break
        "water the plants",
    ]
    sub = parsed["items"][3]
    assert sub["level"] == 1 and sub["parent"] == 3 and sub["detail"] == "Tomorrow"
    assert parsed["items"][4]["level"] == 0 and parsed["items"][4]["parent"] is None
    assert parsed["items"][2]["bold"]


def test_every_line_and_marker_is_accounted_for():
    parsed = rp.group(PAGES)
    s = rp.summarize(parsed)
    assert s["unplaced_lines"] == 0 and s["markers_without_text"] == 0
    assert s["footer_lines"] == 2
    assert s["top_level"] == 5 and s["subtasks"] == 1
    assert s["stated_count_matches"] is True


def test_reports_instead_of_dropping():
    pages = [{"lines": [line("orphan wrap", 0), line("real item", 1)], "markers": [marker(1), marker(5)]}]
    parsed = rp.group(pages)
    assert [u["text"] for u in parsed["unplaced"]] == ["orphan wrap"]
    assert parsed["markers_without_text"] == 1
    assert [it["text"] for it in parsed["items"]] == ["real item"]


def test_page_with_no_markers_places_nothing():
    parsed = rp.group([{"lines": [line("just prose", 0)], "markers": []}])
    assert parsed["items"] == [] and len(parsed["unplaced"]) == 1


def test_markdown_nests_subtasks():
    md = rp.to_markdown(rp.group(PAGES))
    assert md.startswith("# Errands\n")
    assert "- [ ] **plan the trip**\n  - [ ] book a train _(Tomorrow)_\n" in md
