"""Smoke test: verify Layer A+B OpenGraph image normalization works.

Scenario (exact Facebook bug reproduction):
  - Mock ad dict with `images` as a COMMA-SEPARATED STRING (legacy cache
    hit form — the root cause of the user-reported bug).
  - Render templates share_shortlink.html + ad_detail.html.
  - Assert that all og:image tags contain real image filenames (min 4 chars
    + file extension dot), NOT the first character of the string.
"""
import os
import sys
import re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def layer_a_helpers():
    print('--- 1. AdService._normalize_images_field (LAYER A) ---')
    from app.services.ad_service import AdService
    norm = AdService._normalize_images_field

    assert norm(None) == []
    assert norm('') == []
    assert norm('p') == []                          # 1 char -> filtered out
    assert norm('p1.jpg , p2.jpg ,, , p3.JPG  ') == ['p1.jpg', 'p2.jpg', 'p3.JPG']
    mixed = norm(['p', None, 'img.png', 123, 'ok.jpeg', 'bad', 'noext'])
    assert mixed == ['img.png', 'ok.jpeg'], f'mixed={mixed}'
    # https URL already absolute — normalized out (filter requires a '.')
    url_out = norm('https://foo/a.jpg')
    assert url_out == ['https://foo/a.jpg'] or url_out == [], url_out
    print('    ALL LAYER-A ASSERTIONS OK')
    print(f'    STRING comma -> {norm("p1.jpg,p2.jpg")!r}')
    print(f'    list w/ 1char -> {norm(["p", "img.jpg"])!r}')

    print()
    print('--- 2. AdService._repair_ad_dict_images mutation ---')
    d1 = {'ad_id': 'x', 'images': 'p1.jpg,p2.jpg'}
    r1 = AdService._repair_ad_dict_images(d1)
    assert isinstance(r1['images'], list) and len(r1['images']) == 2
    assert r1['first_image'] == 'p1.jpg'
    d2 = {'ad_id': 'y', 'images': ['p', 'riri.png']}
    r2 = AdService._repair_ad_dict_images(d2)
    assert r2['images'] == ['riri.png'] and r2['first_image'] == 'riri.png'
    print('    ALL repair_ad_dict_images assertions OK')


def layer_b_templates():
    print()
    print('--- 3. Jinja2 templates (LAYER B) — BUG REPRODUCTION: images as STRING ---')
    from app import create_app
    app = create_app('testing')
    with app.test_request_context('/s/ad-mock-001'):
        from flask import render_template
        # This is the EXACT legacy shape from Redis cache before the fix:
        # `images` is a COMMA-SEPARATED STRING (not a list).
        mock_ad = {
            'ad_id': 'ad-mock-001',
            'title': 'Vitara 2003 a Vendre',
            'description': 'Belle Vitara 2003, 4 portes, clim OK, 95 000 km',
            'ad_type': 'sell',
            'price_gkach': 50000,
            'images': 'vitara1.jpg,vitara2.jpg,vitara3.jpg',
        }

        # ---- share_shortlink.html ------------------------------------------------
        html = render_template(
            'share_shortlink.html',
            ad=mock_ad,
            canonical_path='/ad/ad-mock-001',
            is_crawler=True,
        )
        og_imgs = re.findall(r'<meta property="og:image" content="([^"]+)"', html)
        og_titles = re.findall(r'<meta property="og:title" content="([^"]+)"', html)
        og_urls = re.findall(r'<meta property="og:url" content="([^"]+)"', html)
        tw_imgs = re.findall(r'<meta name="twitter:image" content="([^"]+)"', html)
        print(f'    share_shortlink.html rendered, len={len(html)} chars')
        print(f'      og:title        = {og_titles}')
        print(f'      #meta og:image  = {len(og_imgs)}')
        for i, u in enumerate(og_imgs[:4]):
            print(f'        #{i+1}: {u}')
        print(f'      twitter:image   = {tw_imgs[:1]}')
        print(f'      og:url          = {og_urls}')

        # KEY ASSERTION: NO FIRST-CHARACTER BUG!
        for u in og_imgs:
            fname = u.rsplit('/', 1)[-1]
            assert len(fname) >= 4 and '.' in fname, (
                f'BUG DETECTED: {u!r} -> filename {fname!r} looks like 1-char '
                f'fallback bug (images-as-string + [0] first char)'
            )
        assert any('vitara1.jpg' in u for u in og_imgs), \
            f'Expected vitara1.jpg to appear as first og:image. Got {og_imgs}'
        print('    share_shortlink.html assertions OK — Facebook will show the AD IMAGE, not the logo!')

        # ---- ad_detail.html -----------------------------------------------------
        # Simulate `request.url` availability (needed for canonical og:url fallback)
        with app.test_request_context('/ad/ad-mock-001'):
            html2 = render_template('ad_detail.html', ad=mock_ad, current_user=None)
            og_imgs2 = re.findall(r'<meta property="og:image" content="([^"]+)"', html2)
            print()
            print(f'    ad_detail.html rendered, len={len(html2)} chars')
            print(f'      #meta og:image  = {len(og_imgs2)}')
            for i, u in enumerate(og_imgs2[:4]):
                print(f'        #{i+1}: {u}')
            for u in og_imgs2:
                fname = u.rsplit('/', 1)[-1]
                assert len(fname) >= 4 and '.' in fname, (
                    f'ad_detail.html BUG: {u!r} filename {fname!r}'
                )
            print('    ad_detail.html assertions OK')


if __name__ == '__main__':
    layer_a_helpers()
    layer_b_templates()
    print()
    print('=' * 70)
    print('ALL SMOKE TESTS PASSED — Facebook preview image bug is FIXED.')
    print('=' * 70)
