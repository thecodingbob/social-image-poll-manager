import math
import random
from datetime import timedelta
from enum import Enum

from glob import glob
from pathlib import Path
from typing import List, Dict, Tuple
from os import path

import jsonpickle
from PIL import Image
from facebook import GraphAPI

from social_poll_manager import utils
from social_poll_manager.image_utils import  compose


class Reaction(object):
    def __init__(self, name: str, image: Image.Image, emoji: str):
        self.name = name
        self.image = image.convert("RGBA")
        self.emoji = emoji

    def super_impose(self, image: Image):
        lower_size = min(image.width, image.height)
        padding = int(lower_size * 0.05)
        reaction_size = int(lower_size / 5)
        resized_reaction_image = self.image.resize((reaction_size, reaction_size))
        image.paste(resized_reaction_image, (padding, padding), resized_reaction_image)


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
            self.reactions[participant.assigned_reaction].super_impose(image)
            images.append(image)
        while layout[0] * layout[1] > (len(participants) + 1):
            reduced_dim = max(layout) - 1
            layout = (min(layout), reduced_dim)
        return compose(images, layout)

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
