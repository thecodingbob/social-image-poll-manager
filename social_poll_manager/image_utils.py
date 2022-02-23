import os
import re
from typing import List, Tuple
from os import path

import requests
from PIL import Image
from facebook import GraphAPI

from social_poll_manager import utils

logger = utils.get_logger(__name__)


def compose(images: List[Image.Image], layout: Tuple[int, int]):
    width = images[0].width
    height = images[0].height
    result = Image.new("RGB", (width * layout[0], height * layout[1]))
    for i in range(layout[0]):
        for j in range(layout[1]):
            idx = (i * layout[1]) + j
            if idx == len(images):
                return result
            result.paste(images[idx], (i * width, j * height))
    return result


def collect_images_from_albums(album_ids: list[str], graph_api: GraphAPI, target_directory: str) -> None:
    def extract_original_post_id(post_message: str) -> str:
        fb_id_pattern = r"facebook\.com/(\d*)"
        try:
            return re.search(fb_id_pattern, post_message).group(1)
        except AttributeError:
            logger.warning(f"Unable to get original id from Facebook post message: {post_message}", exc_info=True)

    done_file = path.join(target_directory, ".done")

    if path.exists(done_file):
        logger.info("Photos already downloaded. Skipping collection.")
    else:
        logger.info("Starting fb image collection...")

        os.makedirs(target_directory, exist_ok=True)

        downloaded = 0
        skipped = 0
        failed = 0

        for album_id in album_ids:
            logger.info(f"Scraping album with id {album_id}...")
            for image_connection in graph_api.get_all_connections(album_id, connection_name="photos"):
                if "Original post" in image_connection["name"]:
                    image_id = extract_original_post_id(image_connection["name"])
                else:
                    image_id = image_connection["id"]
                image_path = path.join(target_directory, f"{image_id}.jpg")
                if not path.exists(image_path):
                    image_data = graph_api.get_object(id=image_id, fields="images")
                    best_image_link = max(image_data["images"], key=lambda im: im["height"])["source"]
                    logger.info(f"Downloading image with id {image_id} from url {best_image_link}.")
                    try:
                        with open(image_path, "wb") as im_file:
                            im_file.write(requests.get(best_image_link).content)
                        downloaded += 1
                    except:
                        failed += 1
                        logger.warning(f"Unable to download and save image with connection data: {image_connection}",
                                       exc_info=True)
                else:
                    skipped += 1
                    logger.info(f"Image f{image_path} already present in directory. Skipping download.")

        logger.info(f"Finished collecting images.\nDownloaded:{downloaded}\nSkipped:{skipped}\nFailed:{failed}")
        if failed == 0:
            with open(done_file, "w") as f:
                pass
