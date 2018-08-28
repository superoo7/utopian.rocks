import constants
import json
from beem.account import Account
from beem.amount import Amount
from beem.comment import Comment
from beem.vote import Vote
from contribution import Contribution
from datetime import datetime, date, timedelta
from dateutil.parser import parse


class User():
    def __init__(self, row):
        self.name = row[0].replace("\n", "").rstrip()
        self.ban_length = float(row[1])
        self.ban_start = parse(row[2])
        self.banned = row[3]


def contribution(row, status):
    """
    Convert row to dictionary, only selecting values we want.
    """
    contribution = Contribution(row)
    url = contribution.url

    if url == "":
        return

    if contribution.staff_pick.lower() == "yes":
        staff_picked = True
    else:
        staff_picked = False

    try:
        review_date = parse(contribution.review_date)
    except Exception:
        review_date = datetime(1970, 1, 1)

    if (datetime.now() - review_date).days > 7 and status != "unreviewed":
        return

    total_payout = 0

    # Check if post deleted
    try:
        comment = Comment(url)
    except Exception:
        return

    # Calculate total (pending) payout of contribution
    if comment.time_elapsed() > timedelta(days=7):
        total_payout = Amount(comment.json()["total_payout_value"]).amount
    else:
        total_payout = Amount(comment.json()["pending_payout_value"]).amount

    # Get votes, comments and author
    votes = comment.json()["net_votes"]
    comments = comment.json()["children"]
    author = comment.author

    # Add status for unvoted and pending
    if contribution.vote_status == "Unvoted":
        status = "unvoted"
    elif contribution.vote_status == "Pending":
        status = "pending"

    # Check if contribution was voted on
    if contribution.vote_status == "Yes":
        voted_on = True
        try:
            utopian_vote = Vote(f"{comment.authorperm}|utopian-io").sbd
        except Exception:
            voted_on = False
            utopian_vote = 0
    else:
        voted_on = False
        utopian_vote = 0

    # Check for when contribution not reviewed
    if contribution.score == "":
        score = None
    else:
        try:
            score = float(contribution.score)
        except Exception:
            score = None

    # Create contribution dictionary and return it
    new_contribution = {
        "moderator": contribution.moderator.strip(),
        "author": author,
        "review_date": review_date,
        "url": url,
        "repository": contribution.repository,
        "category": contribution.category,
        "staff_picked": staff_picked,
        "picked_by": contribution.picked_by,
        "status": status,
        "score": score,
        "voted_on": voted_on,
        "total_payout": total_payout,
        "total_votes": votes,
        "total_comments": comments,
        "utopian_vote": utopian_vote,
        "created": comment["created"],
        "title": comment.title
    }

    return new_contribution


def get_reviewed():
    """
    Return all the rows in the most recent two review worksheets.
    """
    previous = constants.PREVIOUS_REVIEWED.get_all_values()
    current = constants.CURRENT_REVIEWED.get_all_values()
    reviewed = previous[1:] + current[1:]
    return reviewed


def get_unreviewed():
    """
    Return all the rows in the unreviewed worksheet.
    """
    unreviewed = constants.UNREVIEWED.get_all_values()
    return unreviewed[1:]


def update_posts():
    """
    Adds all reviewed and unreviewed contributions to the database.
    """
    reviewed = []
    unreviewed = []

    # Iterate over all worksheets in the spreadsheet
    reviewed = get_reviewed()
    unreviewed = get_unreviewed()

    # Convert row to dictionary
    reviewed = [contribution(x, "reviewed") for x in reviewed]
    unreviewed = [contribution(x, "unreviewed") for x in unreviewed]

    # Lazy so drop database and replace
    contributions = constants.DB.contributions

    for post in reviewed + unreviewed:
        if post:
            contributions.replace_one({"url": post["url"]}, post, True)


def update_banned():
    users = constants.DB.users

    for user in constants.BANNED_USERS.get_all_values()[1:]:
        try:
            user = User(user)
        except ValueError:
            continue

        banned_until = user.ban_start + timedelta(days=user.ban_length)
        user.banned_until = banned_until

        if user.banned == "Yes":
            user.banned = True
        else:
            user.banned = False

        users.update({"name": user.name}, user.__dict__, upsert=True)


def update_account():
    account = Account("utopian-io")
    current_vp = account.get_voting_power()
    recharge_time = account.get_recharge_time_str(99.75)
    recharge_timedelta = account.get_recharge_timedelta(99.75)

    if recharge_time == 0:
        recharge_class = "recharge--low"
    elif recharge_timedelta > timedelta(hours=1):
        recharge_class = "recharge--high"
    elif (recharge_timedelta < timedelta(hours=1) and
          recharge_timedelta > timedelta(minutes=30)):
        recharge_class = "recharge--average"
    else:
        recharge_class = "recharge--low"

    accounts = constants.DB.accounts
    accounts.replace_one(
        {"account": "utopian-io"},
        {
            "account": "utopian-io",
            "current_vp": current_vp,
            "recharge_time": recharge_time,
            "recharge_class": recharge_class,
            "updated": datetime.now()
        }
    )


def main():
    update_posts()
    update_account()
    update_banned()

if __name__ == '__main__':
    main()
