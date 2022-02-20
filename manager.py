import math
import os
import random
import re
from configparser import ConfigParser, SectionProxy
from enum import Enum
from typing import List, Dict, Tuple

import requests
from facebook import GraphAPI
from datetime import timedelta
from PIL import Image
from os import path
from glob import glob
from pathlib import Path
import jsonpickle

import utils

logger = utils.get_logger(__name__)


class Reaction(object):
    def __init__(self, name: str, image: Image.Image, emoji: str):
        self.name = name
        self.image = image.convert("RGBA")
        self.emoji = emoji


def _super_impose(image: Image.Image, reaction: Reaction):
    lower_size = min(image.width, image.height)
    padding = int(lower_size * 0.05)
    reaction_size = int(lower_size / 5)
    resized_reaction = reaction.image.resize((reaction_size, reaction_size))
    image.paste(resized_reaction, (padding, padding), resized_reaction)


def _compose(images: List[Image.Image], layout: Tuple[int, int]):
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


class ImageData(object):

    def __init__(self, image_id: str, image_path: str, fb_url: str = None):
        self.image_id = image_id
        self.image_path = image_path
        self.fb_url = fb_url


class MatchStatus(Enum):
    GENERATED = "generated"
    POSTED = "posted"
    OVER = "over"


class MatchParticipantData:

    def __init__(self, image_data: ImageData, assigned_reaction: str):
        self.image_data = image_data
        self.assigned_reaction = assigned_reaction
        self.reactions = 0


class MatchData(object):

    def __init__(self, participants: list[MatchParticipantData], match_number: int):
        self.match_status = MatchStatus.GENERATED
        self.participants = participants
        self.post_id: str = ""
        self.match_number = match_number


class PhaseData(object):

    def __init__(self, participants: List[ImageData], phase_number: int):
        self.participants = participants
        self.matches: List[MatchData] = []
        self.phase_number = phase_number


class PollData(object):

    def __init__(self, images: Dict[str, ImageData]):
        self.images = images
        self.phases: List[PhaseData] = []


class PollManager:

    def __init__(self, graph_api: GraphAPI, reactions: List[Reaction], layout: Tuple[int],
                 max_posts_per_time: int, poll_name: str, voting_duration: timedelta = timedelta(hours=6),
                 poll_data_file: str = "poll_data.json", winner_album_id: str = None,
                 album_id: str = None, pics_dir: str = "./pics", winners_per_match: int = 1,
                 interactive_mode: bool = False, original_urls_enabled: bool = False):

        self.logger = utils.get_logger(__class__.__name__)

        self.graph_api = graph_api
        self.reactions = dict()
        for reaction in reactions:
            self.reactions[reaction.name] = reaction
        self.layout = layout
        self.participants_per_match = self.layout[0] * self.layout[1]
        self.max_posts_per_time = max_posts_per_time
        self.voting_duration = voting_duration
        self.poll_name = poll_name
        self.album_id = album_id
        self.pics_dir = pics_dir
        self.winner_album_id = winner_album_id
        self.winners_per_match = winners_per_match
        self.interactive_mode = interactive_mode
        self.original_urls_enabled = original_urls_enabled
        self.poll_data_file = poll_data_file
        self.poll_data = self._init_poll_data()
        self.logger.info("Done initializing.")

    def _save_poll_data(self):
        utils.safe_json_dump(self.poll_data_file, self.poll_data)

    def _init_poll_data(self) -> PollData:
        try:
            with open(self.poll_data_file) as f:
                data = jsonpickle.decode(f.read())
                self.logger.info(f"Successfully loaded poll data.")
                return data
        except FileNotFoundError:
            self.logger.warning("File containing poll data not found. Starting fresh.", exc_info=False)
            images = dict()
            image_paths = glob(path.join(self.pics_dir, "*.jpg"))
            for image_path in image_paths:
                im_id = Path(image_path).stem
                images[im_id] = ImageData(image_id=im_id,
                                          image_path=image_path,
                                          fb_url=f"https://facebook.com/{im_id}" if self.original_urls_enabled else None)
            poll_data = PollData(images)
            first_phase = PhaseData(list(images.values()), 1)
            poll_data.phases.append(first_phase)
            return poll_data

    def _generate_match_image(self, participants: List[MatchParticipantData], layout: Tuple[int, int]):
        images = []
        for participant in participants:
            image = Image.open(participant.image_data.image_path)
            _super_impose(image, self.reactions[participant.assigned_reaction])
            images.append(image)
        while layout[0] * layout[1] > (len(participants) + 1):
            reduced_dim = max(layout) - 1
            layout = (min(layout), reduced_dim)
        return _compose(images, layout)

    def _generate_matches(self):
        current_phase_data = self.poll_data.phases[-1]
        participants = current_phase_data.participants
        random.shuffle(participants)
        match_number = int(math.ceil(len(participants) / self.participants_per_match))
        participant_idx = 0
        for i in range(match_number - 2):
            match_participants: List[MatchParticipantData] = []
            match_participants_num = self.participants_per_match
            if i == match_number - 2:
                remaining_participants = len(participants) - participant_idx
                # avoid auto win on last match
                if remaining_participants == self.participants_per_match - 1:
                    match_participants_num -= 1
            elif i == match_number - 1:
                match_participants_num = len(participants) - participant_idx
            reactions = list(self.reactions.values())
            random.shuffle(reactions)
            for j in range(match_participants_num):
                match_participant = MatchParticipantData(participants[participant_idx], reactions[j].name)
                match_participants.append(match_participant)
                participant_idx += 1
            current_phase_data.matches.append(MatchData(match_participants, i + 1))
        self._save_poll_data()

    def start(self):
        # test_participants = []
        # for i in range(4):
        #     test_participants.append(MatchParticipantData(self.poll_data.phases[0].participants[i], self.reactions[i]))
        # # _super_impose(test_im, reaction=self.reactions[0])
        # random.shuffle(self.reactions)
        # test_im = _generate_match_image(test_participants, (2, 3))
        # test_im.show()
        self._generate_matches()


def init_reactions(config: SectionProxy) -> list[Reaction]:
    base_dir = config.get("base_dir")
    names = config.get("names").split(",")
    emojis = config.get("emojis").split(",")
    image_names = config.get("images").split(",")
    reactions = []
    for (idx, image_name) in enumerate(image_names):
        image = Image.open(path.join(base_dir, image_names[idx]))
        reactions.append(Reaction(names[idx], image, emojis[idx]))
    return reactions


def collect_images_from_albums(album_ids: list[str], graph_api: GraphAPI, target_directory: str) -> None:
    def extract_original_post_id(post_message: str) -> str:
        fb_id_pattern = r"facebook\.com/(\d*)"
        try:
            return re.search(fb_id_pattern, post_message).group(1)
        except AttributeError:
            logger.warning(f"Unable to get original id from Facebook post message: {post_message}", exc_info=True)

    done_file = path.join(target_directory, "done")

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


def main():
    resources_dir = "resources"
    config = ConfigParser(allow_no_value=True)
    config.read('config.ini', encoding='utf-8')

    reactions = init_reactions(config["reactions"])

    fb_settings = config["facebook"]
    bot_settings = config["bot_settings"]

    page_id = fb_settings.get("page_id")
    access_token = fb_settings.get("access_token")
    # If album_id is missing, posts to timeline (using page_id)
    album_id = fb_settings.get("album_id", fallback=page_id)
    winner_album_id = fb_settings.get("winner_album_id")
    graph_api = GraphAPI(access_token=access_token, timeout=3000)

    pics_dir = bot_settings.get("images_folder")
    images_source = bot_settings.get("images_source")
    if images_source == "ALBUM":
        source_albums_ids = bot_settings.get("source_albums_ids").split(",")
        collect_images_from_albums(album_ids=source_albums_ids, graph_api=graph_api, target_directory=pics_dir)
    layout = tuple([int(x) for x in bot_settings.get("layout").split("x")])
    max_posts_per_time = bot_settings.getint("max_posts_per_time")
    voting_duration = timedelta(seconds=utils.parse_duration(bot_settings.get("voting_duration")))
    winners_per_match = bot_settings.getint("winners_per_match")
    poll_name = bot_settings.get("poll_name")
    og_urls_enabled = bot_settings.getboolean("og_urls_enabled")

    poll_manager = PollManager(graph_api=graph_api, album_id=album_id, winner_album_id=winner_album_id,
                               pics_dir=pics_dir, reactions=reactions, layout=layout,
                               max_posts_per_time=max_posts_per_time,
                               voting_duration=voting_duration, poll_name=poll_name,
                               original_urls_enabled=og_urls_enabled, winners_per_match=winners_per_match,
                               poll_data_file=path.join(resources_dir, "poll_data.json"))

    poll_manager.start()


if __name__ == "__main__":
    main()
