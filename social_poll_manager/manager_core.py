import math
import random
import time
from datetime import timedelta, datetime
from enum import Enum

from glob import glob
from io import BytesIO
from pathlib import Path
from typing import List, Dict, Tuple, Union
from os import path

import jsonpickle
from PIL import Image
from facebook import GraphAPI

from social_poll_manager import utils
from social_poll_manager.image_utils import compose
from social_poll_manager.utils import auto_str_and_repr


@auto_str_and_repr
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


@auto_str_and_repr
class ImageData(object):

    def __init__(self, image_id: str, image_path: str, fb_url: str = None):
        self.image_id = image_id
        self.image_path = image_path
        self.fb_url = fb_url


class MatchStatus(Enum):
    # Match just generated
    GENERATED = "generated"
    # Match posted to facebook
    POSTED = "posted"
    # Match over, reactions registered
    OVER = "over"


class PhaseStatus(Enum):
    # Phase just created
    CREATED = "created"
    # Matches generated, phase running, some matches could already be posted but not all
    GENERATED = "generated"
    # ALl matches are posted
    POSTED = "posted"
    # All matches are over, so is the pase
    OVER = "over"


@auto_str_and_repr
class MatchParticipantData:

    def __init__(self, image_data: ImageData, assigned_reaction: str):
        self.image_data = image_data
        self.assigned_reaction = assigned_reaction
        self.reactions = 0


@auto_str_and_repr
class MatchData(object):

    def __init__(self, participants: list[MatchParticipantData], match_number: int):
        self.match_status = MatchStatus.GENERATED
        self.participants = participants
        self.post_id: Union[str, None] = None
        self.match_number = match_number
        self.posted_time: Union[datetime, None] = None


@auto_str_and_repr
class PhaseData(object):

    def __init__(self, participants: List[ImageData], phase_number: int):
        self.participants = participants
        self.matches: List[MatchData] = []
        self.phase_number = phase_number
        self.status = PhaseStatus.CREATED


@auto_str_and_repr
class PollData(object):

    def __init__(self, images: Dict[str, ImageData]):
        self.images = images
        self.phases: List[PhaseData] = []


class PollManager:

    def __init__(self, graph_api: GraphAPI, reactions: List[Reaction], layout: Dict[int, Tuple],
                 max_posts_per_time: int, poll_name: str, post_message: str, page_id: str,
                 max_participants_per_match: int, winner_message: Union[str, None] = None,
                 voting_duration: timedelta = timedelta(hours=6), post_interval: timedelta = timedelta(hours=1),
                 poll_data_file: str = "poll_data.json", winner_album_id: str = None,
                 album_id: str = None, pics_dir: str = "./pics",
                 interactive_mode: bool = False, original_urls_enabled: bool = False):

        self.logger = utils.get_logger(__class__.__name__)

        self.graph_api = graph_api
        self.reactions = dict()
        for reaction in reactions:
            self.reactions[reaction.name] = reaction
        self.layout = layout
        self.max_participants_per_match = max_participants_per_match
        self.max_posts_per_time = max_posts_per_time
        self.voting_duration = voting_duration
        self.post_interval = post_interval
        self.poll_name = poll_name
        self.page_id = page_id
        self.album_id = album_id
        self.pics_dir = pics_dir
        self.winner_album_id = winner_album_id
        self.interactive_mode = interactive_mode
        self.original_urls_enabled = original_urls_enabled
        self.post_message = post_message.replace("\\n", "\n")
        self.winner_message = winner_message
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

    def upload_photo(self, image: Union[str, BytesIO], message: str, album: str = None) -> str:
        """
        Uploads a photo to a specific album, or to the news feed if no album id is specified.
        :param image: The image to be posted. Could be a path to an image file or a BytesIO object containing the image
        data
        :param message: The message used as image description
        :param album: The album where to post the image
        :return the resulting post id
        """
        if album is None or album == "":
            album = self.page_id
        uploaded = False
        retry_count = 0
        while not uploaded:
            try:
                if type(image) == str:
                    with open(image, "rb") as im:
                        page_post_id = \
                            self.graph_api.put_photo(image=im, message=message, album_path=album + "/photos")[
                                'id']
                else:
                    page_post_id = \
                        self.graph_api.put_photo(image=image.getvalue(), message=message, album_path=album + "/photos")[
                            'id']
                uploaded = True
            except Exception as e:
                self.logger.warning("Exception occurred during photo upload.", exc_info=True)
                if retry_count < 5:
                    self.logger.warning("Retrying photo upload...")
                    time.sleep(60 * 30 if "spam" in str(e) else 180)
                else:
                    self.logger.error("Unable to post even after several retries. Check what's happening. Bot is"
                                      " shutting down.")
                    exit()
                retry_count += 1
        return page_post_id

    def _generate_match_image(self, participants: List[MatchParticipantData], layout: Tuple[int]) -> BytesIO:
        if (layout[0] * layout[1]) != len(participants):
            raise ValueError(f"Called _generate_match_image() with inconsistent layout and participant list length:"
                             f"{len(participants)} & {layout}")
        images = []
        for participant in participants:
            image = Image.open(participant.image_data.image_path)
            self.reactions[participant.assigned_reaction].super_impose(image)
            images.append(image)
        composed = compose(images, layout)
        jpeg_bytes = BytesIO()
        composed.save(jpeg_bytes, "JPEG", quality=80)
        return jpeg_bytes

    def _get_current_phase(self) -> PhaseData:
        return self.poll_data.phases[-1]

    def _is_final_phase(self) -> bool:
        current_phase = self._get_current_phase()
        if current_phase.status == PhaseStatus.CREATED:
            raise RuntimeError("Called _is_final_phase() without generating matches first!")
        return len(current_phase.matches) == 1

    def _is_playoff_phase(self) -> bool:
        previous_phase = self.poll_data.phases[-2]
        return len(previous_phase.matches) == 1

    def _generate_matches(self):
        current_phase_data = self._get_current_phase()
        participants = current_phase_data.participants
        random.shuffle(participants)
        match_number = int(math.ceil(len(participants) / self.max_participants_per_match))
        participant_idx = 0
        for i in range(match_number):
            match_participants: List[MatchParticipantData] = []
            match_participants_num = self.max_participants_per_match
            if i == match_number - 2:
                remaining_participants = len(participants) - participant_idx
                # avoid auto win on last match
                if remaining_participants == self.max_participants_per_match + 1:
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
        current_phase_data.status = PhaseStatus.GENERATED
        self._save_poll_data()

    def _post_match(self, match: MatchData):
        current_phase = self._get_current_phase()
        if current_phase.status != PhaseStatus.GENERATED:
            raise RuntimeError(f"Invoked _post_match() while phase is not in the generated status!")
        if match.match_status != MatchStatus.GENERATED:
            raise RuntimeError(f"Invoked _post_match() while match is not in the generated status!")
        message = self.post_message \
            .replace("$POLL_NAME$", self.poll_name) \
            .replace("$PHASE_NUMBER$", str(current_phase.phase_number)) \
            .replace("$MATCH_NUMBER$", str(match.match_number)) \
            .replace("$TOTAL_MATCHES$", str(len(current_phase.matches)))
        if self._is_final_phase():
            message += "\nFINAL MATCH"
        elif self._is_playoff_phase():
            message += "\nPLAYOFF MATCH"
        match.post_id = self.upload_photo(
            self._generate_match_image(match.participants, self.layout[len(match.participants)]),
            message,
            self.album_id)
        match.match_status = MatchStatus.POSTED
        match.posted_time = datetime.now()
        if self.original_urls_enabled:
            participants_urls = [f"{self.reactions[participant.assigned_reaction].emoji}: " \
                                 f"{participant.image_data.fb_url}"
                                 for participant in match.participants]
            comment_message = "\n".join(participants_urls)
            self.graph_api.put_comment(match.post_id, comment_message)
        self._save_poll_data()

    def _post_loop(self):
        phase_data = self._get_current_phase()
        if phase_data.status != PhaseStatus.GENERATED:
            raise RuntimeError(f"Invoked _post_loop() while phase is not in the running status!")
        posted = 0
        for match in self._get_current_phase().matches:
            if match.match_status == MatchStatus.POSTED:
                continue
            self.logger.info(f"Posting match {match}...")
            self._post_match(match)
            self._save_poll_data()
            posted += 1
            if (posted % self.max_posts_per_time) == 0:
                self.logger.info(f"Reached max posts per time limit of {self.max_posts_per_time}.")
                if self.interactive_mode:
                    self.logger.info("Press enter to post the next batch.")
                    input()
                else:
                    self.logger.info(f"Next batch will be posted after {self.post_interval}.")
                    time.sleep(self.post_interval.seconds)
        phase_data.status = PhaseStatus.POSTED
        self._save_poll_data()

    def _get_reactions(self, match: MatchData):
        self.logger.info(f"Getting reactions for match {match.match_number}...")
        page_story_id = self.graph_api.get_object(match.post_id, fields="page_story_id")["page_story_id"]
        for participant in match.participants:
            reacts = self.graph_api.get_object(
                id=page_story_id,
                fields=f"reactions.limit(0).type({participant.assigned_reaction.upper()}).summary(total_count)"
            )["reactions"]["summary"]["total_count"]
            self.logger.info(f"Participant {participant.image_data.image_id} got {reacts} reactions.")
            participant.reactions = reacts

    def _collect_reactions(self):
        matches = self._get_current_phase().matches
        for match in matches:
            if match.match_status == MatchStatus.GENERATED:
                raise RuntimeError(f"Invoked _collect_reactions() while some match was not posted yet!")
            if match.match_status == MatchStatus.OVER:
                continue
            if (match.posted_time + self.voting_duration) > datetime.now():
                raise RuntimeError(f"Invoked _collect_reactions() while some match was not over yet!")
            self._get_reactions(match)
            match.match_status = MatchStatus.OVER
            self._save_poll_data()

    def _wait_for_phase_end(self):
        phase_data = self._get_current_phase()
        if phase_data.status != PhaseStatus.POSTED:
            raise ValueError("Called _wait_for_phase_end() while phase status is not POSTED!")
        latest_post_time = max(phase_data.matches, key=lambda match: match.posted_time).posted_time
        latest_post_time_expire = latest_post_time + self.voting_duration
        if latest_post_time_expire > datetime.now():
            wait_timedelta = latest_post_time_expire - datetime.now()
            self.logger.info(f"Phase {phase_data.phase_number} will end in {wait_timedelta}. Sleeping until then.")
            time.sleep(wait_timedelta.seconds)
        self.logger.info(f"Phase {phase_data.phase_number} is over. Collecting data...")
        self._collect_reactions()
        phase_data.status = PhaseStatus.OVER
        self._save_poll_data()

    def _handle_current_phase(self):
        phase_data = self._get_current_phase()
        phase_number = phase_data.phase_number
        if phase_data.status == PhaseStatus.CREATED:
            self.logger.info(f"Generating matches for phase {phase_number}...")
            self._generate_matches()
        if phase_data.status == PhaseStatus.GENERATED:
            self.logger.info(f"Starting post loop for phase {phase_number}...")
            self._post_loop()
        if phase_data.status == PhaseStatus.POSTED:
            self.logger.info(f"All the matches for phase {phase_number} have been posted. Now waiting for "
                             f"completion.")
            self._wait_for_phase_end()

    def _generate_next_phase(self):
        previous_phase_data = self._get_current_phase()
        if previous_phase_data.status != PhaseStatus.OVER:
            raise RuntimeError(f"Invoked _generate_next_phase() while last phase was not over yet!")
        phase_number = previous_phase_data.phase_number + 1
        self.logger.info(f"Generating data for phase {phase_number}...")
        phase_winners = []
        for match in previous_phase_data.matches:
            if match.match_status != MatchStatus.OVER:
                raise RuntimeError(f"Invoked _generate_next_phase() while one of the phase matches was not over yet!")
            winner_reactions = max(match.participants, key=lambda participant: participant.reactions).reactions
            winners_data = filter(lambda participant: participant.reactions == winner_reactions, match.participants)
            phase_winners += [self.poll_data.images[winner.image_data.image_id] for winner in winners_data]
        new_phase_data = PhaseData(phase_winners, phase_number)
        self.poll_data.phases.append(new_phase_data)
        self._save_poll_data()

    def _handle_poll_end(self):
        winner = self.poll_data.phases[-1].participants[0]
        self.logger.info(f"Poll finished! Winner is {winner}")
        if self.winner_album_id is not None:
            winner_message = self.winner_message.replace("$POLL_NAME$", self.poll_name)
            if self.original_urls_enabled:
                winner_message += f"\n\nOriginal post: {winner.fb_url}"
            self.upload_photo(winner.image_path, message=winner_message, album=self.winner_album_id)

    def start(self):
        while len(self._get_current_phase().participants) > 1:
            self._handle_current_phase()
            if self.interactive_mode:
                self.logger.info(f"Phase {self._get_current_phase().phase_number} is over. Press enter to "
                                 f"proceed with next phase.")
                input()
            self._generate_next_phase()
        self._handle_poll_end()
