"""An item's photos: what is kept of an upload, and the files and rows.

The photos are made here with Pillow, so every case is a real image, and
written to the photo_dir fixture's folder, never to data/photos.
"""

import io
import os

import pytest
from PIL import Image

import dependencies
import photos
import psells
from helpers import (FORM_TOKEN_FIELD, add_product, add_sale, forms,
                     log_in, paragraphs)


def jpeg(size=(400, 300), exif=None, **save):
    out = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(out, "JPEG", exif=exif or b"",
                                               **save)
    return out.getvalue()


def opened(data):
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


# What is kept of one upload ----------------------------------------------------

def test_a_large_photo_is_kept_at_1600_pixels_on_its_long_side():
    kept = opened(photos.prepare(jpeg((4000, 3000)), "a.jpg"))

    assert kept.format == "JPEG"
    assert kept.size == (1600, 1200)


def test_a_small_photo_is_not_enlarged():
    assert opened(photos.prepare(jpeg((800, 600)), "a.jpg")).size == (800, 600)


def test_a_photo_stored_sideways_is_turned_the_right_way_up():
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90 degrees to display

    kept = opened(photos.prepare(jpeg((400, 200), exif=exif), "a.jpg"))

    assert kept.size == (200, 400)


def test_the_location_and_every_other_tag_are_dropped():
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    exif[0x8825] = {1: "N", 2: (43.0, 39.0, 0.0), 3: "W", 4: (79.0, 23.0, 0.0)}
    xmp = (b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf='
           b'"http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description '
           b'exif:GPSLatitude="43,39N"/></rdf:RDF></x:xmpmeta>')
    upload = jpeg(exif=exif, xmp=xmp, comment=b"taken at home")
    assert opened(upload).getexif().get_ifd(0x8825)  # the test photo has one

    kept_bytes = photos.prepare(upload, "a.jpg")
    kept = opened(kept_bytes)

    assert len(kept.getexif()) == 0
    assert not {"exif", "xmp", "comment"} & set(kept.info)
    assert b"GPS" not in kept_bytes and b"PhoneMaker" not in kept_bytes
    assert b"taken at home" not in kept_bytes


def test_an_rgb_colour_profile_is_kept():
    # Any bytes do: Pillow carries the profile without reading it.
    upload = jpeg(icc_profile=b"profile bytes")

    assert opened(photos.prepare(upload, "a.jpg")).info.get(
        "icc_profile") == b"profile bytes"


def test_a_transparent_png_is_kept_as_a_jpeg_on_white():
    out = io.BytesIO()
    Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(out, "PNG")

    kept = opened(photos.prepare(out.getvalue(), "a.png"))

    assert kept.format == "JPEG"
    assert all(channel > 250 for channel in kept.getpixel((5, 5)))


@pytest.mark.parametrize("label, data, sentence", [
    ("a.gif", None, "a.gif is not a JPEG or PNG photo. Export it as JPEG"),
    ("a.heic", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64,
     "a.heic could not be read as a photo."),
    ("a.jpg", b"", "a.jpg could not be read as a photo."),
    ("cut.jpg", "cut", "cut.jpg could not be read as a photo."),
])
def test_what_is_not_a_jpeg_or_png_photo_is_refused(label, data, sentence):
    if data is None:
        out = io.BytesIO()
        Image.new("RGB", (10, 10)).save(out, "GIF")
        data = out.getvalue()
    elif data == "cut":
        data = jpeg((400, 300))[:300]

    with pytest.raises(photos.PhotoError, match=sentence.replace(".", r"\.")):
        photos.prepare(data, label)


def test_a_photo_over_25_mb_is_refused(monkeypatch):
    data = jpeg()
    monkeypatch.setattr(photos, "MAX_PHOTO_BYTES", len(data) - 1)

    with pytest.raises(photos.PhotoError, match="a.jpg is over 25 MB"):
        photos.prepare(data, "a.jpg")


# pytest.ini makes every warning an error, which would hide whether prepare
# does so itself; here warnings behave as they do in the running app.
@pytest.mark.filterwarnings("default")
def test_a_photo_with_too_many_pixels_is_refused_before_it_is_decoded(
        monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 400 * 300 - 1)

    with pytest.raises(photos.PhotoError, match="too many pixels"):
        photos.prepare(jpeg((400, 300)), "a.jpg")


# The files and the rows -------------------------------------------------------

def files(folder):
    return sorted(os.listdir(folder)) if folder.exists() else []


def test_photos_are_kept_as_files_with_a_row_each(db, photo_dir):
    add_product(db, 1, quantity_received=1)

    assert photos.add_photos(db, 1, [("a.jpg", jpeg()), ("b.jpg", jpeg())]) == 2

    rows = photos.product_photos(db, 1)
    assert [row["product_id"] for row in rows] == [1, 1]
    assert files(photo_dir) == sorted(row["file_name"] for row in rows)
    for row in rows:
        assert row["file_name"].endswith(".jpg")
        with open(photos.path_of(row), "rb") as kept:
            assert opened(kept.read()).format == "JPEG"


def test_one_bad_photo_keeps_none_of_the_upload(db, photo_dir):
    add_product(db, 1, quantity_received=1)

    with pytest.raises(photos.PhotoError, match="b.gif"):
        photos.add_photos(db, 1, [("a.jpg", jpeg()), ("b.gif", b"GIF89a")])

    assert photos.product_photos(db, 1) == []
    assert files(photo_dir) == []


def test_files_written_are_removed_when_the_rows_cannot_be(db, photo_dir,
                                                          monkeypatch):
    add_product(db, 1, quantity_received=1)
    db.execute("INSERT INTO photos (product_id, file_name) "
               "VALUES (1, 'taken.jpg')")
    names = iter(["fresh", "taken"])
    monkeypatch.setattr(photos.uuid, "uuid4",
                        lambda: type("U", (), {"hex": next(names)})())

    with pytest.raises(Exception):
        photos.add_photos(db, 1, [("a.jpg", jpeg()), ("b.jpg", jpeg())])

    assert files(photo_dir) == []


@pytest.mark.parametrize("count, sentence", [
    (0, "Choose at least one photo."),
    (11, "Up to 10 photos at a time; 11 were chosen."),
])
def test_an_upload_carries_one_to_ten_photos(db, photo_dir, count, sentence):
    add_product(db, 1, quantity_received=1)

    with pytest.raises(photos.PhotoError, match=sentence):
        photos.add_photos(db, 1, [("a.jpg", jpeg())] * count)


def test_photos_for_a_product_that_does_not_exist_are_refused(db, photo_dir):
    with pytest.raises(psells.ProductNotFound):
        photos.add_photos(db, 9, [("a.jpg", jpeg())])
    assert files(photo_dir) == []


def test_deleting_a_photo_removes_its_row_and_its_file(db, photo_dir):
    add_product(db, 1, quantity_received=1)
    photos.add_photos(db, 1, [("a.jpg", jpeg()), ("b.jpg", jpeg())])
    first, second = photos.product_photos(db, 1)

    assert photos.delete_photo(db, first["id"])["id"] == first["id"]

    assert photos.product_photos(db, 1) == [second]
    assert files(photo_dir) == [second["file_name"]]
    assert photos.delete_photo(db, first["id"]) is None


def test_a_photo_whose_file_is_already_gone_still_deletes(db, photo_dir):
    add_product(db, 1, quantity_received=1)
    photos.add_photos(db, 1, [("a.jpg", jpeg())])
    (photo,) = photos.product_photos(db, 1)
    os.remove(photos.path_of(photo))

    photos.delete_photo(db, photo["id"])

    assert photos.product_photos(db, 1) == []


@pytest.mark.parametrize("name", ["../config.json", "a/b.jpg", ".hidden"])
def test_a_stored_name_that_leaves_the_folder_is_never_a_path(name):
    with pytest.raises(ValueError):
        photos.path_of({"file_name": name})


def test_a_product_with_photos_is_deleted_only_once_they_are(db, photo_dir):
    add_product(db, 1, quantity_received=1)
    photos.add_photos(db, 1, [("a.jpg", jpeg()), ("b.jpg", jpeg())])

    assert psells.deletion_blocker(db, 1) is None
    assert psells.photo_blocker(db, 1) == (
        "This product has 2 photos. Delete them from its Edit page first, "
        "then delete the product.")
    with pytest.raises(psells.DeleteRefused, match="2 photos"):
        psells.delete_product(db, 1)

    for photo in photos.product_photos(db, 1):
        photos.delete_photo(db, photo["id"])
    assert psells.photo_blocker(db, 1) is None
    psells.delete_product(db, 1)


def test_a_photo_makes_an_item_photographed(db, partner_rate, photo_dir):
    add_product(db, 1, quantity_received=1, listed_price_cents=None)
    assert [p["id"] for p in psells.pipeline(db)["Photographed"]] == []

    photos.add_photos(db, 1, [("a.jpg", jpeg())])

    assert [p["id"] for p in psells.pipeline(db)["Photographed"]] == [1]


# The pages ----------------------------------------------------------------------

def upload_form(client, product_id=1):
    (form,) = [form for form in forms(
        client.get(f"/products/{product_id}/edit").text)
        if form["action"].endswith("/photos")]
    return form


def upload(client, *named, product_id=1):
    """Post through the Edit page's own upload form, each (name, bytes) as a
    browser sends a chosen file. Nothing chosen sends what a browser sends:
    one part with an empty file name, written out by hand because the test
    client leaves an empty file name out, which a browser does not."""
    form = upload_form(client, product_id)
    if named:
        return client.post(
            form["action"], follow_redirects=False,
            files=[("photos", (name, data, "image/jpeg")) for name, data in named])

    body = (b"--boundary\r\n"
            b'Content-Disposition: form-data; name="photos"; filename=""\r\n'
            b"Content-Type: application/octet-stream\r\n\r\n"
            b"\r\n--boundary--\r\n")
    return client.post(
        form["action"], content=body, follow_redirects=False,
        headers={"Content-Type": "multipart/form-data; boundary=boundary"})


def img_sources(html):
    return [src for src in __import__("re").findall(r'<img src="([^"]*)"', html)]


def test_the_edit_page_offers_a_photo_upload(client, db):
    add_product(db, 1, quantity_received=1)

    form = upload_form(client)

    assert form["method"] == "post"
    assert form["enctype"] == "multipart/form-data"
    (picker,) = [field for field in form["inputs"] if field.get("type") == "file"]
    assert picker["name"] == "photos"
    assert picker["accept"] == "image/jpeg,image/png"
    assert "multiple" in picker
    assert "No photos yet." in client.get("/products/1/edit").text


def test_photos_uploaded_show_on_the_edit_page_and_are_served(client, db):
    add_product(db, 1, quantity_received=1)

    response = upload(client, ("a.jpg", jpeg((3000, 2000))), ("b.jpg", jpeg()))

    assert response.status_code == 303
    assert response.headers["location"] == (
        "http://testserver/products/1/edit?photos=added#photos")
    page = client.get("/products/1/edit?photos=added").text
    assert "Photos added." in page
    rows = photos.product_photos(db, 1)
    assert img_sources(page) == [f"http://testserver/photos/{row['id']}"
                                 for row in rows]

    served = client.get(f"/photos/{rows[0]['id']}")
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/jpeg"
    assert served.headers["cache-control"] == "private, max-age=86400"
    with open(photos.path_of(rows[0]), "rb") as kept:
        assert served.content == kept.read()
    assert opened(served.content).size == (1600, 1067)


def test_the_upload_form_works_with_its_hidden_token_alone(client, db):
    add_product(db, 1, quantity_received=1)
    form = upload_form(client)
    (token,) = [field["value"] for field in form["inputs"]
                if field.get("name") == FORM_TOKEN_FIELD]
    del client.headers[dependencies.FORM_TOKEN_HEADER]

    response = client.post(form["action"], data={FORM_TOKEN_FIELD: token},
                           files=[("photos", ("a.jpg", jpeg(), "image/jpeg"))],
                           follow_redirects=False)

    assert response.status_code == 303
    assert len(photos.product_photos(db, 1)) == 1


def test_an_upload_without_the_form_token_is_refused(client, db, photo_dir):
    add_product(db, 1, quantity_received=1)
    del client.headers[dependencies.FORM_TOKEN_HEADER]

    response = client.post("/products/1/photos",
                           files=[("photos", ("a.jpg", jpeg(), "image/jpeg"))])

    assert response.status_code == 403
    assert photos.product_photos(db, 1) == []
    assert files(photo_dir) == []


@pytest.mark.parametrize("named, sentence", [
    ((), "Choose at least one photo."),
    ((("a.jpg", b"not a photo"),), "a.jpg could not be read as a photo."),
])
def test_a_refused_upload_says_why_and_keeps_nothing(client, db, named,
                                                     sentence):
    add_product(db, 1, quantity_received=1)

    response = upload(client, *named)

    assert response.status_code == 422
    assert (paragraphs(response.text, "form-error")[0][0]
            == f"{sentence} No photo was added.")
    assert photos.product_photos(db, 1) == []
    # The product form is still there, filled in as stored.
    assert 'value="Product 1"' in response.text


def test_photos_for_a_product_that_does_not_exist_are_a_404(client, db):
    response = client.post("/products/9/photos",
                           files=[("photos", ("a.jpg", jpeg(), "image/jpeg"))])

    assert response.status_code == 404


def test_a_photo_that_does_not_exist_is_a_404(client, db):
    add_product(db, 1, quantity_received=1)
    upload(client, ("a.jpg", jpeg()))
    (photo,) = photos.product_photos(db, 1)
    os.remove(photos.path_of(photo))

    assert client.get(f"/photos/{photo['id']}").status_code == 404
    assert client.get("/photos/999").status_code == 404
    assert client.get("/photos/999/delete").status_code == 404
    assert client.post("/photos/999/delete").status_code == 404


def test_a_photo_is_deleted_through_its_confirmation_page(client, db,
                                                          photo_dir):
    add_product(db, 1, quantity_received=1)
    upload(client, ("a.jpg", jpeg()), ("b.jpg", jpeg()))
    first, second = photos.product_photos(db, 1)

    page = client.get(f"/photos/{first['id']}/delete").text
    (form,) = forms(page)
    assert img_sources(page) == [f"http://testserver/photos/{first['id']}"]
    # Seeing the page deletes nothing.
    assert len(photos.product_photos(db, 1)) == 2

    response = client.post(form["action"], follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == (
        "http://testserver/products/1/edit?photos=deleted#photos")
    assert photos.product_photos(db, 1) == [second]
    assert files(photo_dir) == [second["file_name"]]
    assert "Photo deleted." in client.get(
        "/products/1/edit?photos=deleted").text


def test_a_notice_word_not_known_shows_nothing(client, db):
    add_product(db, 1, quantity_received=1)

    page = client.get("/products/1/edit?photos=<b>hi</b>").text

    assert paragraphs(page, "notice") == []


def test_a_product_with_photos_offers_no_delete_until_they_are_gone(client, db):
    add_product(db, 1, quantity_received=1)
    upload(client, ("a.jpg", jpeg()))

    page = client.get("/products/1/delete").text

    assert paragraphs(page, "form-error")[0][0] == (
        "This product has 1 photo. Delete it from its Edit page first, then "
        "delete the product.")
    assert forms(page) == []
    assert client.post("/products/1/delete").status_code == 409
    assert psells.find_items_by_name_or_category(psells.all_products(db),
                                                 "Product 1")


# Downloads ------------------------------------------------------------------------

def test_each_photo_downloads_named_by_its_item_and_place(client, db):
    add_product(db, 1, quantity_received=1)
    upload(client, ("IMG_0001.jpg", jpeg()), ("IMG_0002.jpg", jpeg()))
    first, second = photos.product_photos(db, 1)

    page = client.get("/products/1/edit").text
    assert f'href="http://testserver/photos/{second["id"]}/download"' in page

    response = client.get(f"/photos/{second['id']}/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["content-disposition"] == (
        'attachment; filename="psells-1-2.jpg"')
    with open(photos.path_of(second), "rb") as kept:
        assert response.content == kept.read()


def test_download_all_is_one_zip_of_every_photo_in_order(client, db):
    import zipfile

    add_product(db, 1, quantity_received=1)
    upload(client, ("a.jpg", jpeg((300, 200))), ("b.jpg", jpeg((200, 300))))
    rows = photos.product_photos(db, 1)

    page = client.get("/products/1/edit").text
    assert 'href="http://testserver/products/1/photos.zip"' in page

    response = client.get("/products/1/photos.zip")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == (
        'attachment; filename="psells-1-photos.zip"')
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["psells-1-1.jpg", "psells-1-2.jpg"]
        for name, row in zip(archive.namelist(), rows):
            assert archive.getinfo(name).compress_type == zipfile.ZIP_STORED
            with open(photos.path_of(row), "rb") as kept:
                assert archive.read(name) == kept.read()


def test_an_item_without_photos_offers_no_download_and_has_no_zip(client, db):
    add_product(db, 1, quantity_received=1)

    assert "photos.zip" not in client.get("/products/1/edit").text
    assert client.get("/products/1/photos.zip").status_code == 404
    assert client.get("/products/9/photos.zip").status_code == 404
    assert client.get("/photos/999/download").status_code == 404


def test_the_upload_hint_states_the_limits_photos_py_applies(client, db,
                                                             monkeypatch):
    # The demo's, as photos.py sets them when PSELLS_DEMO is 1.
    monkeypatch.setattr(photos, "MAX_PHOTOS_PER_UPLOAD", 3)
    monkeypatch.setattr(photos, "MAX_PHOTO_MB", 8)
    add_product(db, 1, quantity_received=1)

    page = " ".join(client.get("/products/1/edit").text.split())

    assert "JPEG or PNG, up to 3 at a time, 8 MB each." in page
