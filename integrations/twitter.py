import os
import sys
import argparse
from dataclasses import dataclass
from typing import List

import tweepy
from dotenv import load_dotenv
from loguru import logger

from integrations.integration import Integration, TodoistTaskRequest

@dataclass
class XPost:
    """
    Represents a post (formerly tweet) retrieved from the X API via Tweepy.
    Stores the post ID, its text, and a direct link to the post on X.
    """
    post_id: str
    text: str
    post_link: str

class XApiError(Exception):
    """
    Custom exception to handle errors when interacting with X (formerly Twitter) via Tweepy.
    """
    pass

class XApiClient:
    """
    A client for interacting with X (formerly Twitter) using the Tweepy library.
    Provides methods to authenticate and fetch posts.
    """

    def __init__(self, bearer_token: str,
                 consumer_key: str,
                 consumer_secret: str,
                 access_token: str,
                 access_token_secret: str) -> None:
        """
        Initialize the Tweepy client with the provided credentials.
        
        wait_on_rate_limit=True will automatically handle rate limit errors by waiting until the limit resets.
        """
        if not bearer_token:
            raise XApiError("Bearer token not provided.")
        if not consumer_key or not consumer_secret or not access_token or not access_token_secret:
            raise XApiError("Missing consumer or access tokens. Please check your environment variables.")

        self.client = tweepy.Client(
            bearer_token=bearer_token,
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            wait_on_rate_limit=True
        )

    def get_user_id(self, username: str) -> str:
        """
        Retrieve the user ID of the specified username.
        """
        try:
            user = self.client.get_user(username=username)
            if not user or not user.data:
                raise XApiError(f"User '{username}' not found.")
            return str(user.data.id)
        except tweepy.TweepyException as exc:
            raise XApiError(f"Error fetching user ID: {exc}")

    def fetch_posts(self, user_id: str, username: str, max_results: int) -> List[XPost]:
        """
        Retrieves up to max_results recent posts from the user with the given ID.
        Also includes direct links to each post on X.
        """
        try:
            tweets_response = self.client.get_users_tweets(
                id=user_id,
                max_results=min(max_results, 100),
                tweet_fields=["id", "text"]
            )
            if not tweets_response or not tweets_response.data:
                return []
            posts = []
            for tweet in tweets_response.data:
                post_id = str(tweet.id)
                post_text = tweet.text
                # Build a direct link to this post.
                post_link = f"https://x.com/{username}/status/{post_id}"
                posts.append(XPost(post_id=post_id, text=post_text, post_link=post_link))
            return posts
        except tweepy.TweepyException as exc:
            raise XApiError(f"Error fetching posts: {exc}")

def load_env_variables():
    """
    Loads environment variables from a .env file.  
    Required environment variables:
      - X_BAERER_TOKEN  
      - X_API_KEY       (Consumer Key)  
      - X_API_KEY_SECRET (Consumer Secret)  
      - X_ACCESS_TOKEN  
      - X_ACCESS_TOKEN_SECRET  
    """
    load_dotenv()
    bearer_token = os.getenv("X_BAERER_TOKEN")
    consumer_key = os.getenv("X_API_KEY")
    consumer_secret = os.getenv("X_API_KEY_SECRET")
    access_token = os.getenv("X_ACCESS_TOKEN")
    access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET")

    if not bearer_token:
        sys.exit("Error: Bearer token is not set in environment variables.")
    if not consumer_key or not consumer_secret or not access_token or not access_token_secret:
        sys.exit("Error: One or more Twitter keys/tokens are not set in environment variables.")

    return bearer_token, consumer_key, consumer_secret, access_token, access_token_secret


class XIntegration(Integration):
    """
    Child class of Integration that fetches posts from tracked X users once a week,
    then converts those posts into TodoistTaskRequest items.
    """

    def __init__(
        self,
        name: str,
        frequency: float,
        bearer_token: str,
        consumer_key: str,
        consumer_secret: str,
        access_token: str,
        access_token_secret: str,
        tracked_users: List[str],
        project_id: int
    ):
        """
        Initialize with required tokens, tracked users, and a target project ID.
        """
        super().__init__(name, frequency)
        self.x_api_client = XApiClient(
            bearer_token, consumer_key, consumer_secret, access_token, access_token_secret
        )
        self.tracked_users = tracked_users
        self.project_id = project_id

    def _tick(self) -> List[TodoistTaskRequest]:
        """
        Fetches up to 100 posts from each tracked user if at least a week has passed.
        Converts them into TodoistTaskRequest objects.
        """


        all_tasks: List[TodoistTaskRequest] = []
        for username in self.tracked_users:
            logger.info(f"Fetching posts from user '{username}'...")
            try:
                user_id = self.x_api_client.get_user_id(username)
                logger.info(f"User ID for '{username}': {user_id}")
                posts = self.x_api_client.fetch_posts(user_id, username, max_results=100)
                logger.info(f"Fetched {len(posts)} posts from user '{username}'.")

                # Convert each post into a TodoistTaskRequest
                for post in posts:
                    # Example: Use post text as the content, link as description
                    new_task = TodoistTaskRequest(
                        content=post.text[:50],
                        description=f"Link: {post.post_link}\nID: {post.post_id}",
                        project_id=self.project_id,
                        due_date=None,
                        priority=4
                    )
                    all_tasks.append(new_task)
            except XApiError as exc:
                logger.error(f"Error while fetching posts for user '{username}': {exc}")

        logger.info(f"Generated {len(all_tasks)} TodoistTaskRequest items in total.")
        return all_tasks

def main():
    """
    Main function to run the XIntegration class.
    """
    bearer_token, consumer_key, consumer_secret, access_token, access_token_secret = load_env_variables()

    # Example: Track posts from these users
    tracked_users = ["mtyrolski"]
    project_id = 1234567890

    x_integration = XIntegration(
        name="X Integration",
        frequency=604800.0,  # One week in seconds
        bearer_token=bearer_token,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        tracked_users=tracked_users,
        project_id=project_id
    )

    requests = x_integration.tick()
    logger.info(f"Generated {len(requests)} tasks from X posts.")
    for request in requests:
        logger.info(f"Task: {request}")
        
if __name__ == "__main__":
    main()