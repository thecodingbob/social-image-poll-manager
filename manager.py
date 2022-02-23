from configparser import ConfigParser, SectionProxy

from facebook import GraphAPI
from datetime import timedelta
from PIL import Image
from os import path

from social_poll_manager.image_utils import collect_images_from_albums
from social_poll_manager.manager_core import Reaction, PollManager

from social_poll_manager import utils

logger = utils.get_logger(__name__)


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
    post_interval = timedelta(seconds=utils.parse_duration(bot_settings.get("post_interval")))
    poll_name = bot_settings.get("poll_name")
    og_urls_enabled = bot_settings.getboolean("og_urls_enabled")
    post_message = bot_settings.get("message")
    winner_message = bot_settings.get("winner_message")
    interactive_mode = bot_settings.getboolean("interactive_mode")

    poll_manager = PollManager(graph_api=graph_api, album_id=album_id, winner_album_id=winner_album_id,
                               pics_dir=pics_dir, reactions=reactions, layout=layout,
                               max_posts_per_time=max_posts_per_time,
                               voting_duration=voting_duration, poll_name=poll_name,
                               original_urls_enabled=og_urls_enabled,
                               poll_data_file=path.join(resources_dir, "poll_data.json"),
                               post_interval=post_interval, post_message=post_message, winner_message= winner_message,
                               interactive_mode=interactive_mode)

    poll_manager.start()


if __name__ == "__main__":
    main()
