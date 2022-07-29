
from os import getenv
from dataclasses import (
    dataclass,
    fields
)
from contextlib import AsyncExitStack

from aiogram import (
    Bot,
    Dispatcher,
    executor,
    exceptions
)
from aiogram.types import ChatMemberStatus

import aiobotocore.session


#######
#
#   SECRETS
#
######

# Ask @alexkuk for .env


BOT_TOKEN = getenv('BOT_TOKEN')

AWS_KEY_ID = getenv('AWS_KEY_ID')
AWS_KEY = getenv('AWS_KEY')

DYNAMO_ENDPOINT = getenv('DYNAMO_ENDPOINT')


######
#
#   OBJ
#
#####


def obj_annots(obj):
    for field in fields(obj):
        yield field.name, field.type


####
#   VOTING
######


@dataclass
class Voting:
    poll_id: str
    chat_id: int

    candidate_message_id: int
    start_message_id: int
    poll_message_id: int

    candidate_user_id: int
    starter_user_id: int

    ban_user_ids: [int]
    no_ban_user_ids: [int]

    min_votes: int


######
#
#  DYNAMO
#
######


######
#   MANAGER
######


async def dynamo_client():
    session = aiobotocore.session.get_session()
    manager = session.create_client(
        'dynamodb',

        # Always ru-central1 for YC
        # https://cloud.yandex.ru/docs/ydb/docapi/tools/aws-setup
        region_name='ru-central1',

        endpoint_url=DYNAMO_ENDPOINT,
        aws_access_key_id=AWS_KEY_ID,
        aws_secret_access_key=AWS_KEY,
    )

    # https://github.com/aio-libs/aiobotocore/discussions/955
    exit_stack = AsyncExitStack()
    client = await exit_stack.enter_async_context(manager)
    return exit_stack, client


######
#  OPS
#####


N = 'N'
S = 'S'
NS = 'NS'


async def dynamo_put(client, table, item):
    await client.put_item(
        TableName=table,
        Item=item
    )


async def dynamo_get(client, table, key_name, key_type, key_value):
    response = await client.get_item(
        TableName=table,
        Key={
            key_name: {
                key_type: str(key_value)
            }
        }
    )
    return response.get('Item')


async def dynamo_delete(client, table, key_name, key_type, key_value):
    await client.delete_item(
        TableName=table,
        Key={
            key_name: {
                key_type: str(key_value)
            }
        }
    )


######
#   DE/SERIALIZE
####


def dynamo_type(annot):
    if annot == int:
        return N
    elif annot == str:
        return S
    elif annot == [int]:
        return NS


def dynamo_parse_value(value, annot):
    if annot == int:
        return int(value)
    elif annot == str:
        return value
    elif annot == [int]:
        return [int(_) for _ in value]


def dynamo_format_value(value, annot):
    if annot == int:
        return str(value)
    elif annot == str:
        return value
    elif annot == [int]:
        return [str(_) for _ in value]


def dynamo_parse_item(item, cls):
    kwargs = {}
    for name, annot in obj_annots(cls):
        type = dynamo_type(annot)
        value = item[name][type]
        value = dynamo_parse_value(value, annot)
        kwargs[name] = value
    return cls(**kwargs)


def dynamo_format_item(obj):
    item = {}
    for name, annot in obj_annots(obj):
        value = getattr(obj, name)
        value = dynamo_format_value(value, annot)
        type = dynamo_type(annot)
        item[name] = {type: value}
    return item


######
#   READ/WRITE
######


VOTINGS_TABLE = 'votings'
POLL_ID_KEY = 'poll_id'


async def put_voting(db, voting):
    item = dynamo_format_item(voting)
    await dynamo_put(db.client, VOTINGS_TABLE, item)


async def get_voting(db, poll_id):
    item = await dynamo_get(
        db.client, VOTINGS_TABLE,
        POLL_ID_KEY, S, poll_id
    )
    if not item:
        return
    return dynamo_parse_item(item, Voting)


async def delete_voting(db, poll_id):
    await dynamo_delete(
        db.client, VOTINGS_TABLE,
        POLL_ID_KEY, S, poll_id
    )


######
#  DB
#######


class DB:
    def __init__(self):
        self.exit_stack = None
        self.client = None

    async def connect(self):
        self.exit_stack, self.client = await dynamo_client()

    async def close(self):
        await self.exit_stack.aclose()


DB.put_voting = put_voting
DB.get_voting = get_voting
DB.delete_voting = delete_voting


#####
#
#  HANDLERS
#
#####


START_TEXTS = [
    '/voteban',
    '/voteban@bandugan_bot',
    '@bandugan_bot',

    '@banof',
    '@banofbot',
]

QUESTION_TEXT = 'Забанить {mention}? ⚖️'
BAN_TEXT = 'Забанить'
NO_BAN_TEXT = 'Не банить'
OPTION_TEXTS = [
    BAN_TEXT,
    NO_BAN_TEXT
]

IS_ADMIN_TEXT = '{mention} админ'

MIN_VOTES = 1


async def handle_start_voting(context, message):
    if not message.reply_to_message:
        return

    if message.text not in START_TEXTS:
        return

    candidate_message_id = message.reply_to_message.message_id
    candidate_user = message.reply_to_message.from_user

    member = await context.bot.get_chat_member(
        chat_id=message.chat.id,
        user_id=candidate_user.id
    )
    if ChatMemberStatus.is_chat_admin(member.status):
        await message.answer(
            text=IS_ADMIN_TEXT.format(
                mention=candidate_user.mention
            )
        )
        return

    start_message_id = message.message_id
    starter_user_id = message.from_user.id

    message = await message.answer_poll(
        question=QUESTION_TEXT.format(
            mention=candidate_user.mention
        ),
        options=[
            BAN_TEXT,
            NO_BAN_TEXT,
        ],
        is_anonymous=False,
    )

    voting = Voting(
        poll_id=message.poll.id,
        chat_id=message.chat.id,

        candidate_message_id=candidate_message_id,
        start_message_id=start_message_id,
        poll_message_id=message.message_id,

        candidate_user_id=candidate_user.id,
        starter_user_id=starter_user_id,

        ban_user_ids=[],
        no_ban_user_ids=[],

        min_votes=MIN_VOTES,
    )
    await context.db.put_voting(voting)


async def safe_delete_message(bot, **kwargs):
    try:
        await bot.delete_message(**kwargs)
    except exceptions.MessageToDeleteNotFound:
        return


async def handle_poll_vote(context, poll_answer):
    voting = await context.db.get_voting(poll_answer.poll_id)

    # revote
    user_id = poll_answer.user.id
    for user_ids in [voting.ban_user_ids, voting.no_ban_user_ids]:
        if user_id in user_ids:
            user_ids.remove(user_id)

    if poll_answer.option_ids:
        # allows_multiple_answers=False
        option_id = poll_answer.option_ids[0]
        option_text = OPTION_TEXTS[option_id]

        if option_text == BAN_TEXT:
            voting.ban_user_ids.append(user_id)
        elif option_text == NO_BAN_TEXT:
            voting.no_ban_user_ids.append(user_id)

    ban = len(voting.ban_user_ids) >= voting.min_votes
    no_ban = len(voting.no_ban_user_ids) >= voting.min_votes
    if ban or no_ban:
        if ban:
            await context.bot.ban_chat_member(
                chat_id=voting.chat_id,
                user_id=voting.candidate_user_id,
            )
            await safe_delete_message(
                context.bot,
                chat_id=voting.chat_id,
                message_id=voting.candidate_message_id
            )

        for message_id in [voting.start_message_id, voting.poll_message_id]:
            await safe_delete_message(
                context.bot,
                chat_id=voting.chat_id,
                message_id=message_id
            )

    await context.db.put_voting(voting)


def setup_handlers(context):
    context.dispatcher.register_message_handler(context.handle_start_voting)
    context.dispatcher.register_poll_answer_handler(context.handle_poll_vote)


#######
#
#  BOT
#
#######


########
#   WEBHOOK
######


async def on_startup(context, _):
    await context.db.connect()


async def on_shutdown(context, _):
    await context.db.close()


PORT = getenv('PORT', 8080)


def run(context):
    executor.start_webhook(
        dispatcher=context.dispatcher,

        webhook_path='/',
        port=PORT,

        on_startup=context.on_startup,
        on_shutdown=context.on_shutdown,

        # Disable aiohttp "Running on ... Press CTRL+C"
        # Polutes YC Logging
        print=None
    )


########
#   CONTEXT
######


class BotContext:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.dispatcher = Dispatcher(self.bot)
        self.db = DB()


BotContext.handle_start_voting = handle_start_voting
BotContext.handle_poll_vote = handle_poll_vote

BotContext.setup_handlers = setup_handlers

BotContext.on_startup = on_startup
BotContext.on_shutdown = on_shutdown
BotContext.run = run


######
#
#   MAIN
#
#####


if __name__ == '__main__':
    context = BotContext()
    context.setup_handlers()
    context.run()
