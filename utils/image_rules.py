from PIL import Image
import io

def validate_character_image(image_bytes):

    img = Image.open(io.BytesIO(image_bytes))

    w, h = img.size

    ratio = w / h

    target = float(os.getenv("CARD_IMAGE_RATIO_TARGET", "0.6666667"))
    tol = float(os.getenv("CARD_IMAGE_RATIO_TOLERANCE", "0.05"))

    if abs(ratio - target) > tol:
        return False

    return True
