"""An item's photos: made ready to keep, stored as files, and recorded.

A photo is a file on disk, in PHOTOS_DIR, and a row in the photos table that
says which item it belongs to. The file is not the upload: prepare reads the
upload with Pillow, turns it the right way up, shrinks it to LONG_SIDE pixels
on its long side and writes it again as a JPEG with no metadata, so the
location a phone records in a photo never reaches the disk. Every photo is
named by PSells, never by the uploader, so a name can neither collide nor
point outside the folder.

PHOTOS_DIR resolves beside this file unless PSELLS_PHOTOS names another
folder; in the container it is the photos volume.
"""

import io
import os
import uuid
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

import psells

PHOTOS_DIR = psells.path_from_environment("PSELLS_PHOTOS", "data", "photos")

# What one upload may carry. nginx refuses a request over its own limit before
# it reaches the app; these say which photo was too big, and why.
MAX_PHOTO_BYTES = 25 * 1024 * 1024
MAX_PHOTOS_PER_UPLOAD = 10

LONG_SIDE = 1600
JPEG_QUALITY = 85
FORMATS = ("JPEG", "PNG")


class PhotoError(ValueError):
    """An upload that cannot be kept, with a sentence safe to show a person.
    Nothing from the upload is kept when one is raised."""


def prepare(data, label):
    """The photo to keep for one upload, as JPEG bytes, or PhotoError.

    label is what the person called the file, for the sentence. Pillow's own
    limit on pixels is kept: an image claiming more is refused before it is
    decoded, which is what stops a small file that would unpack to gigabytes.
    Past the limit Pillow only warns, up to twice it, so here the warning is
    made an error too.
    """
    if len(data) > MAX_PHOTO_BYTES:
        raise PhotoError(f"{label} is over 25 MB.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))

        with image:
            if image.format not in FORMATS:
                raise PhotoError(f"{label} is not a JPEG or PNG photo. "
                                 "Export it as JPEG and upload it again.")

            # A phone stores a photo sideways with a tag saying which way is
            # up. The tag is about to be dropped, so turn the pixels first.
            image = ImageOps.exif_transpose(image)

            # The colour profile only describes RGB pixels; a CMYK profile on
            # converted pixels would be wrong.
            profile = image.info.get("icc_profile") if image.mode == "RGB" else None

            if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
                rgba = image.convert("RGBA")
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.getchannel("A"))
            else:
                image = image.convert("RGB")

            image.thumbnail((LONG_SIDE, LONG_SIDE), Image.Resampling.LANCZOS)

            # Pillow writes what info holds (EXIF, XMP, comments) when it
            # saves, and any of them can carry a location. Emptied, then only
            # the profile is given back.
            image.info = {}
            kept = io.BytesIO()
            image.save(kept, "JPEG", quality=JPEG_QUALITY, optimize=True,
                       icc_profile=profile)
            return kept.getvalue()

    except PhotoError:
        raise
    except (Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise PhotoError(f"{label} has too many pixels.") from error
    # What Pillow raises for a file that is not an image, is cut short or is
    # malformed inside: one sentence for all of them.
    except (UnidentifiedImageError, OSError, SyntaxError,
            ValueError) as error:
        raise PhotoError(f"{label} could not be read as a photo.") from error


def path_of(photo):
    """Where a photo row's file is. The name is PSells' own, but it is checked
    anyway, since a path built from a stored value is a path someone could
    have changed."""
    name = photo["file_name"]
    if os.path.basename(name) != name or name.startswith("."):
        raise ValueError(f"not a photo file name: {name!r}")
    return os.path.join(PHOTOS_DIR, name)


def add_photos(connection, product_id, uploads):
    """Keep every upload for one product, or none of them.

    uploads is a list of (label, bytes). Every photo is prepared before any
    file is written, so one bad photo keeps nothing. Each file is written
    under a temporary name and renamed into place, so a half-written file is
    never one a row points at; if recording the rows fails, the files just
    written are removed. Returns how many were kept.
    """
    if not uploads:
        raise PhotoError("Choose at least one photo.")

    if len(uploads) > MAX_PHOTOS_PER_UPLOAD:
        raise PhotoError(f"Up to {MAX_PHOTOS_PER_UPLOAD} photos at a time; "
                         f"{len(uploads)} were chosen.")

    if connection.execute("SELECT 1 FROM products WHERE id = %s",
                          (product_id,)).fetchone() is None:
        raise psells.ProductNotFound(f"No product with id {product_id}.")

    prepared = [prepare(data, label) for label, data in uploads]

    os.makedirs(PHOTOS_DIR, exist_ok=True)
    written = []

    try:
        for jpeg in prepared:
            name = f"{uuid.uuid4().hex}.jpg"
            path = os.path.join(PHOTOS_DIR, name)
            partial = path + ".partial"
            with open(partial, "xb") as f:
                f.write(jpeg)
                f.flush()
                os.fsync(f.fileno())
            os.replace(partial, path)
            written.append(path)

        with connection.transaction():
            for path in written:
                connection.execute(
                    "INSERT INTO photos (product_id, file_name) VALUES (%s, %s)",
                    (product_id, os.path.basename(path)))
    except BaseException:
        for path in written:
            _remove(path)
        raise

    return len(written)


def product_photos(connection, product_id):
    """One product's photos, in the order they were added."""
    return connection.execute(
        "SELECT * FROM photos WHERE product_id = %s ORDER BY added_at, id",
        (product_id,)).fetchall()


def find_photo(connection, photo_id):
    """The photo with this id, or None."""
    return connection.execute(
        "SELECT * FROM photos WHERE id = %s", (photo_id,)).fetchone()


def delete_photo(connection, photo_id):
    """Delete one photo, its row and then its file. Returns the row, or None
    for an id that does not exist.

    The row goes first: a file left behind by a failure after it is only
    space, while a row whose file had gone would be a broken photo on a page.
    """
    with connection.transaction():
        photo = connection.execute(
            "DELETE FROM photos WHERE id = %s RETURNING *",
            (photo_id,)).fetchone()

    if photo is not None:
        _remove(path_of(photo))

    return photo


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
