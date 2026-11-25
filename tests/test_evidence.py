"""Offline tests for the evidence checks, built from the two real failures seen in Coimbatore."""

from launchscout.evidence import (
    Evidence,
    extract_evidence,
    grounding_problems,
    mention_positions,
    normalize_text,
    normalize_url,
    owns_domain,
)
from launchscout.schemas import MarketResearch

FILLER = " other tutors listed here " * 20  # ~500 characters: pushes text out of the price window


def page(url, text):
    return Evidence(normalize_url(url), normalize_text(text), "page")


def one(name, prices, sources):
    return MarketResearch.model_validate({
        "competitors": [{
            "name": name, "locality": "x", "offering": "x", "schedule": "x", "fit_reason": "x",
            "price_status": "published" if prices else "not_found",
            "prices": [{"label": "fee", "amount_inr": a, "unit": "per month", "source_url": u} for a, u in prices],
            "channels": [], "offers": [], "source_urls": sources,
        }],
        "market_price_context": [],
    })


URBANPRO = "https://www.urbanpro.com/coimbatore/hip-hop-dance-classes"
URBANPRO_PAGE = page(
    URBANPRO,
    "Average monthly fee for 1-1 classes INR 3,600 - 7,200 for 12 classes." + FILLER
    + "Platinum Dsa Dance Academy 5.0 R.S.Puram West, Coimbatore 125 per hour",
)


def test_city_wide_range_is_not_a_competitor_price():
    """The DSA case: the page shows 3,600 (a city range) and 125 (DSA's own fee)."""
    wrong = one("DSA Dance Academy", [(3600, URBANPRO)], [URBANPRO])
    right = one("DSA Dance Academy", [(125, URBANPRO)], [URBANPRO])
    assert any("Rs 3600" in p for p in grounding_problems(wrong, [URBANPRO_PAGE]))
    assert grounding_problems(right, [URBANPRO_PAGE]) == []


def test_padded_source_that_never_names_the_business():
    """The Foot Lock case: a general Justdial category page added only to satisfy the variety rule."""
    justdial = "https://www.justdial.com/Coimbatore/Dance-Classes-For-Bollywood/nct-10153003"
    category = page(justdial, "Dance classes for Bollywood in Coimbatore. Fees depend on class duration.")
    footlock = page(URBANPRO, "Foot Lock Dance School Sitra, Coimbatore 200 per hour")
    research = one("Foot Lock Dance School", [(200, URBANPRO)], [URBANPRO, justdial])
    problems = grounding_problems(research, [category, footlock])
    assert len(problems) == 1 and justdial in problems[0]


def test_price_anywhere_on_the_business_own_website_counts():
    own = "https://www.danceanddance.com/studio/"
    site = page(own, "Welcome to our studio." + FILLER + "Zumba fitness classes Rs 150 per class")
    assert owns_domain(normalize_url(own), "Dance and Dance Studio")
    assert grounding_problems(one("Dance and Dance Studio", [(150, own)], [own]), [site]) == []


def test_price_source_never_seen():
    research = one("X Studio", [(900, "https://never.example.com")], [URBANPRO])
    problems = grounding_problems(research, [page(URBANPRO, "X Studio adults")])
    assert any("never in a search result" in p for p in problems)


def test_name_matching_handles_generic_words_and_ampersand():
    text = normalize_text("Judes Fodas Dance and Fitness Studio, Ganapathy")
    assert mention_positions(text, "Judes Fodas Dance & Fitness Studio")
    assert mention_positions(normalize_text("Hips N Toez Dance Company Madipakkam"), "Hips N Toez")
    assert not mention_positions(normalize_text("Harish teaches salsa"), "Hari")  # whole words only


def test_generic_domain_is_not_owned_by_every_studio():
    assert not owns_domain("dance.com", "Dance and Dance Studio")
    assert owns_domain("swingersdance.com", "The Swingers Dance")
    assert not owns_domain("justdial.com/chennai", "Zero 6 Dance and Fitness Company")


def test_extract_splits_search_results_and_reads_pages():
    messages = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "s1", "function": {"name": "search", "arguments": '{"search_query": "q"}'}},
            {"id": "p1", "function": {"name": "read", "arguments": '{"website_url": "https://a.example.com/fees?ref=1"}'}},
        ]},
        {"role": "tool", "tool_call_id": "s1", "content": repr({"organic": [
            {"title": "A", "link": "https://a.example.com/", "snippet": "Rs 900"},
            {"title": "B", "link": "https://b.example.com/x?srsltid=abc", "snippet": "Rs 700"},
        ]})},
        {"role": "tool", "tool_call_id": "p1", "content": "The following text is scraped website content:\n\nFees Rs 900"},
        {"role": "assistant", "content": "Final answer mentions https://invented.example.com Rs 5"},
    ]
    units = extract_evidence(messages)
    assert [(u.kind, u.url) for u in units] == [
        ("search", "a.example.com"), ("search", "b.example.com/x"), ("page", "a.example.com/fees"),
    ]
    assert all("invented" not in u.url for u in units)  # the agent's own words are never evidence


def test_article_price_well_after_the_name_counts():
    """lbb.in style: name, then a long description, then the fee."""
    lbb = "https://lbb.in/chennai/best-dance-classes-chennai/"
    article = page(lbb, "Leo's Dance Academy, Neelankarai. " + " they teach ballet and salsa" * 15 + " personal classes INR 300 per class")
    assert grounding_problems(one("Leo's Dance Academy", [(300, lbb)], [lbb]), [article]) == []


def test_name_written_as_a_handle():
    ig = "https://www.instagram.com/p/abc/"
    post = page(ig, "coimbatore singanallur movementzfactor class fees kids joining fee 1,200")
    assert grounding_problems(one("Movementz Factor", [(1200, ig)], [ig]), [post]) == []


def test_source_url_never_seen_is_reported_as_such():
    research = one("X Studio", [], ["https://never.example.com"])
    assert any("never in a search result" in p for p in grounding_problems(research, []))


def test_repair_moves_price_to_the_page_that_shows_it():
    """The Swingers case: real price, wrong page cited (their profile instead of the reel)."""
    from launchscout.evidence import repair_claims

    profile, reel = "https://www.instagram.com/swingersdanceofficial/", "https://www.instagram.com/reel/abc/"
    units = [
        Evidence(normalize_url(profile), normalize_text("The Swingers Dance Inc, 35k followers"), "search", profile),
        Evidence(normalize_url(reel), normalize_text("offer at The Swingers Dance Inc 2 month classes 2999"), "search", reel),
    ]
    fixed, notes = repair_claims(one("The Swingers Dance", [(2999, profile)], [profile]), units)
    assert fixed.competitors[0].prices[0].source_url == reel
    assert reel in fixed.competitors[0].source_urls and any("Moved" in n for n in notes)


def test_repair_removes_unsupported_claims_and_empty_competitors():
    from launchscout.evidence import repair_claims

    post = "https://www.instagram.com/p/xyz/"
    other_studio = Evidence(normalize_url(post), normalize_text("at muvfeet fees 999 only Velachery"), "search", post)
    fixed, notes = repair_claims(one("DD Dance & Fitness Studio", [(999, post)], [post]), [other_studio])
    assert fixed.competitors == [] and len(notes) == 3  # source, price, then the competitor itself


def test_google_redirect_is_not_a_source_even_if_it_names_the_business():
    from launchscout.evidence import repair_claims

    goto = "https://www.google.com/goto?url=CAESabc"
    unit = Evidence(normalize_url(goto), normalize_text("Kiki's Dance Studio adults batch monthly fees just 1500"), "search", goto)
    fixed, notes = repair_claims(one("Kiki's Dance Studio", [(1500, goto)], [goto]), [unit])
    assert fixed.competitors == [] and any("redirect" in n for n in notes)


def test_all_generic_name_does_not_match_any_dance_text():
    """Regression: 'Dance and Dance Studio' used to shrink to 'dance' and match every page."""
    text = normalize_text("Adult freestyle dance, Anna Salai, Chennai. Bollywood dance and hip hop classes. Fee just 400")
    assert mention_positions(text, "Dance and Dance Studio") == []
    assert mention_positions(normalize_text("Dance and Dance Studio, Greams Road"), "Dance and Dance Studio")


def test_city_check_removes_business_no_page_places_in_the_city():
    """The Zenith case: real prices on its own site, but nothing says it is in Chennai."""
    from launchscout.evidence import repair_claims

    site = "https://zenithdanceacademy.in/package/"
    unit = page(site, "Zenith Dance Academy packages 8 classes 2,100 12 classes 3,100")
    research = one("Zenith Dance Academy", [(2100, site)], [site])
    kept, _ = repair_claims(research, [unit])  # no city given: kept
    assert len(kept.competitors) == 1
    fixed, notes = repair_claims(research, [unit], city="Chennai")
    assert fixed.competitors == [] and "places it in Chennai" in notes[-1]


def test_city_confirmed_by_text_url_alias_or_locality():
    from launchscout.evidence import located_in, place_names

    jd = Evidence(normalize_url("https://www.justdial.com/Chennai/Zero-6-Dance"), normalize_text("Zero 6 Dance and Fitness Company"), "search")
    old_name = page("https://a.example.com", "Raack Academy of Dance, Kilpauk, Madras")
    area = page("https://b.example.com", "Hips N Toez Dance Company, 5th Cross Street, Madipakkam")
    assert located_in(jd, "Zero 6 Dance and Fitness Company", place_names("Chennai", "unknown"))  # city in the URL
    assert located_in(old_name, "Raack Academy of Dance", place_names("Chennai", "unknown"))  # old city name
    assert located_in(area, "Hips N Toez Dance Company", place_names("Chennai", "Madipakkam / T. Nagar"))
    assert not located_in(area, "Hips N Toez Dance Company", place_names("Chennai", "unknown"))


def test_city_next_to_a_different_business_does_not_count():
    from launchscout.evidence import located_in, place_names

    other = page("https://c.example.com", "Best dance classes in Chennai: Step N Tap, Leo's Dance Academy")
    assert not located_in(other, "Zenith Dance Academy", place_names("Chennai", "unknown"))
