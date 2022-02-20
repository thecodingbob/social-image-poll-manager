from configparser import ConfigParser, SectionProxy
from facebook import GraphAPI
from datetime import timedelta
from PIL import Image
from os import path
import jsonpickle

import utils


class Reaction(object):
    def __init__(self, name: str, image: Image, emoji: str):
        self.name = name
        self.image = image
        self.emoji = emoji


class PollData(object):

    def __init__(self):
        pass


class PollManager:

    def __init__(self, graph_api: GraphAPI, reactions: list[Reaction], layout: tuple[int],
                 max_posts_per_time: int, poll_name: str, voting_duration: timedelta = timedelta(hours=6),
                 poll_data_file: str = "poll_data.json", winner_album_id: str = None,
                 album_id: str = None, pics_dir: str = "./pics",
                 interactive_mode: bool = False):

        self.logger = utils.get_logger(__name__)

        self.graph_api = graph_api
        self.reactions = reactions
        self.layout = layout
        self.max_posts_per_time = max_posts_per_time
        self.voting_duration = voting_duration
        self.poll_name = poll_name
        self.album_id = album_id
        self.pics_dir = pics_dir
        self.winner_album_id = winner_album_id
        self.interactive_mode = interactive_mode
        self.poll_data_file = poll_data_file
        self.poll_data = self._init_poll_data()
        self.logger.info("Done initializing.")

    def _init_poll_data(self) -> PollData:
        try:
            with open(self.poll_data_file) as f:
                data = jsonpickle.decode(f)
                self.logger.info(f"Successfully loaded poll data: {data}")
                return data
        except FileNotFoundError:
            self.logger.warning("File containing poll data not found. Starting fresh.", exc_info=False)
            return PollData()

    def start(self):
        pass


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


def collect_images_from_albums(album_ids: list[str], graph_api: GraphAPI, target_directory: str):
    pass


def main():
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
        source_albums_ids = bot_settings.get("source_albums_id").split(",")
        collect_images_from_albums(album_ids=source_albums_ids, graph_api=graph_api, target_directory=pics_dir)
    layout = tuple([int(x) for x in bot_settings.get("layout").split("x")])
    max_posts_per_time = bot_settings.getint("max_posts_per_time")
    voting_duration = timedelta(seconds=utils.parse_duration(bot_settings.get("voting_duration")))
    poll_name = bot_settings.get("poll_name")

    poll_manager = PollManager(graph_api=graph_api, album_id=album_id, winner_album_id=winner_album_id,
                               pics_dir=pics_dir, reactions=reactions, layout=layout,
                               max_posts_per_time=max_posts_per_time,
                               voting_duration=voting_duration, poll_name=poll_name)

    poll_manager.start()


if __name__ == "__main__":
    main()
