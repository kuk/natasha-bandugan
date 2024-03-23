
import sys
from os import getenv
from dataclasses import (
    dataclass,
    fields
)
import asyncio
from contextlib import AsyncExitStack

from aiogram import (
    Bot,
    Dispatcher,
    executor,
    exceptions
)
from aiogram.types import ChatMemberStatus
from aiogram.dispatcher.middlewares import BaseMiddleware

import aiohttp
import aiobotocore.session


#######
#
#   ENV
#
######

# Ask @alexkuk for .env


BOT_TOKEN = getenv('BOT_TOKEN')

AWS_KEY_ID = getenv('AWS_KEY_ID')
AWS_KEY = getenv('AWS_KEY')

DYNAMO_ENDPOINT = getenv('DYNAMO_ENDPOINT')

CHAT_ID = int(getenv('CHAT_ID'))
ADMIN_ID = int(getenv('ADMIN_ID'))

MODER_API_TOKEN = getenv('MODER_API_TOKEN')


######
#
#   OBJ
#
#####


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


@dataclass
class UserStats:
    chat_id: int
    user_id: int
    message_count: int

    @property
    def key(self):
        return self.chat_id, self.user_id


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


async def dynamo_put(client, table, item):
    await client.put_item(
        TableName=table,
        Item=item
    )


async def dynamo_get(client, table, key_name, key_type, value):
    response = await client.get_item(
        TableName=table,
        Key={
            key_name: {
                key_type: str(value)
            }
        }
    )
    return response.get('Item')


async def dynamo_delete(client, table, key_name, key_type, value):
    await client.delete_item(
        TableName=table,
        Key={
            key_name: {
                key_type: str(value)
            }
        }
    )


######
#   DE/SER
####


def dynamo_deser_value(value, annot):
    if annot == int:
        return int(value)
    elif annot == str:
        return value
    elif annot == [int]:
        return [int(_) for _ in value]


def dynamo_ser_value(value, annot):
    if annot == int:
        return str(value)
    elif annot == str:
        return value
    elif annot == [int]:
        return [str(_) for _ in value]


def obj_annots(obj):
    for field in fields(obj):
        yield field.name, field.type


def annot_key_type(annot):
    if annot == int:
        return 'N'
    elif annot == str:
        return 'S'
    elif annot == [int]:
        return 'NS'


def dynamo_deser_item(item, cls):
    kwargs = {}
    for key_name, annot in obj_annots(cls):
        key_type = annot_key_type(annot)
        value = item[key_name][key_type]
        value = dynamo_deser_value(value, annot)
        kwargs[key_name] = value
    return cls(**kwargs)


def dynamo_ser_item(obj):
    item = {}
    for key_name, annot in obj_annots(obj):
        value = getattr(obj, key_name)
        value = dynamo_ser_value(value, annot)
        key_type = annot_key_type(annot)
        item[key_name] = {key_type: value}
    return item


# On DynamoDB partition key
# https://aws.amazon.com/ru/blogs/database/choosing-the-right-dynamodb-partition-key/


def dynamo_ser_key(parts):
    return '#'.join(
        str(_) for _ in parts
    )


######
#   READ/WRITE
######


async def put_voting(db, obj):
    item = dynamo_ser_item(obj)
    await dynamo_put(db.client, 'votings', item)


async def get_voting(db, key):
    item = await dynamo_get(
        db.client, 'votings',
        'poll_id', 'S', key
    )
    if item:
        return dynamo_deser_item(item, Voting)


async def delete_voting(db, key):
    await dynamo_delete(
        db.client, 'votings',
        'poll_id', 'S', key
    )


async def put_user_stats(db, obj):
    item = dynamo_ser_item(obj)
    item['key'] = {'S': dynamo_ser_key(obj.key)}
    await dynamo_put(db.client, 'user_stats', item)


async def get_user_stats(db, key):
    item = await dynamo_get(
        db.client, 'user_stats',
        'key', 'S', dynamo_ser_key(key)
    )
    if item:
        return dynamo_deser_item(item, UserStats)


async def delete_user_stats(db, key):
    await dynamo_delete(
        db.client, 'user_stats',
        'key', 'S', dynamo_ser_key(key)
    )


######
#  DB
#######


class DB:
    async def connect(self):
        self.exit_stack, self.client = await dynamo_client()

    async def close(self):
        await self.exit_stack.aclose()


DB.put_voting = put_voting
DB.get_voting = get_voting
DB.delete_voting = delete_voting

DB.put_user_stats = put_user_stats
DB.get_user_stats = get_user_stats
DB.delete_user_stats = delete_user_stats


######
#
#   MODER
#
#####


class Moder:
    def __init__(self, api_token=MODER_API_TOKEN):
        self.api_token = api_token

    async def connect(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        await self.session.close()


class ModerError(Exception):
    pass


@dataclass
class ModerPred:
    is_spam: bool
    confidence: float


async def predict(moder, text):
    try:
        response = await moder.session.post(
            'http://pywebsolutions.ru:30/predict',
            timeout=10,
            json={
                'api_token': moder.api_token,
                'text': text,
                'model': 'bert'
            }
        )
    except (
            aiohttp.ClientError,
            asyncio.TimeoutError
    ) as error:
        raise ModerError(str(error))

    if response.status != 200:
        raise ModerError(await response.text())

    # {
    #   "class": 0,
    #   "time_taken": 0.041809797286987305,
    #   "class_names": {
    #     "0": "not spam",
    #     "1": "spam"
    #   },
    #   "confidence": 73.92,
    #   "unique_id": "rcVskO5aGy5DPyp-Lj-",
    #   "balance": 199.60000000000002,
    #   "server_id": 1,
    #   "status": "ok"
    # }

    data = await response.json()
    return ModerPred(
        is_spam=data['class'] == 1,
        confidence=data['confidence']
    )


Moder.predict = predict


async def safe_predict(moder, *args):
    try:
        return await moder.predict(*args)
    except ModerError:
        return


#####
#
#  HANDLERS
#
#####


VOTEBAN_TEXTS = [
    '/voteban',
    '/voteban@bandugan_bot',
    '@bandugan_bot',

    '@banof',
    '@banofbot',  # Auto complete via users list
]

QUESTION_TEXT = 'Забанить {mention}? ⚖️'
BAN_TEXT = 'Забанить'
NO_BAN_TEXT = 'Не банить'
OPTION_TEXTS = [
    BAN_TEXT,
    NO_BAN_TEXT
]

IS_ADMIN_TEXT = '{mention} админ'
USE_REPLY_TEXT = 'Напиши это в реплае на спам'

MODER_BAN_TEXT = 'moder ban, confidence={confidence}'
VOTING_BAN_TEXT = 'voting ban'

READ_DELAY = 5
MIN_VOTES = 10


async def handle_my_chat_member(context, update):
    if (
            update.old_chat_member.status == ChatMemberStatus.LEFT
            and ChatMemberStatus.is_chat_member(update.new_chat_member.status)
            and update.chat.id != CHAT_ID
    ):
        await context.bot.leave_chat(update.chat.id)


async def safe_ban_chat_member(bot, **kwargs):
    try:
        await bot.ban_chat_member(**kwargs)
    except exceptions.BadRequest:  # Participant_id_invalid
        return


async def safe_delete_message(bot, **kwargs):
    try:
        await bot.delete_message(**kwargs)
    except exceptions.MessageToDeleteNotFound:
        return


async def safe_forward_message(bot, **kwargs):
    try:
        await bot.forward_message(**kwargs)
    except exceptions.MessageToForwardNotFound:
        return


async def reply_delay_cleanup(context, orig_message, text):
    reply_message = await orig_message.reply(text=text)
    await context.sleep(READ_DELAY)
    for message in [orig_message, reply_message]:
        await safe_delete_message(
            context.bot,
            chat_id=message.chat.id,
            message_id=message.message_id
        )


async def handle_message(context, message):
    chat_id = message.chat.id
    if chat_id != CHAT_ID:
        return

    user_id = message.from_user.id
    user_stats = await context.db.get_user_stats((chat_id, user_id))
    if not user_stats:
        user_stats = UserStats(
            chat_id, user_id,
            message_count=0
        )
    user_stats.message_count += 1
    await context.db.put_user_stats(user_stats)

    if user_stats.message_count < 10:
        pred = await safe_predict(context.moder, message.text)
        if pred and pred.is_spam:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=MODER_BAN_TEXT.format(
                    confidence=pred.confidence
                )
            )
            await safe_forward_message(
                context.bot,
                chat_id=ADMIN_ID,
                from_chat_id=chat_id,
                message_id=message.message_id
            )

    if message.text not in VOTEBAN_TEXTS:
        return

    if not message.reply_to_message:
        await reply_delay_cleanup(
            context, message,
            text=USE_REPLY_TEXT
        )
        return

    candidate_message_id = message.reply_to_message.message_id
    candidate_user = message.reply_to_message.from_user

    member = await context.bot.get_chat_member(
        chat_id=message.chat.id,
        user_id=candidate_user.id
    )
    if ChatMemberStatus.is_chat_admin(member.status):
        await reply_delay_cleanup(
            context, message,
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


async def handle_poll_answer(context, poll_answer):
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
            await safe_ban_chat_member(
                context.bot,
                chat_id=voting.chat_id,
                user_id=voting.candidate_user_id,
            )
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=VOTING_BAN_TEXT
            )
            await safe_forward_message(
                context.bot,
                chat_id=ADMIN_ID,
                from_chat_id=voting.chat_id,
                message_id=voting.candidate_message_id
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
    context.dispatcher.register_my_chat_member_handler(
        context.handle_my_chat_member
    )
    context.dispatcher.register_message_handler(
        context.handle_message
    )
    context.dispatcher.register_poll_answer_handler(
        context.handle_poll_answer
    )


########
#
#   MIDDLEWARE
#
#####


def log(message):
    print(message, file=sys.stderr, flush=True)


class LoggingMiddleware(BaseMiddleware):
    async def on_pre_process_update(self, update, data):
        log(update)


def setup_middlewares(context):
    middleware = LoggingMiddleware()
    context.dispatcher.middleware.setup(middleware)


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
    await context.moder.connect()


async def on_shutdown(context, _):
    await context.db.close()
    await context.moder.close()


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
        self.moder = Moder()

    async def sleep(self, delay):
        await asyncio.sleep(delay)


BotContext.handle_my_chat_member = handle_my_chat_member
BotContext.handle_message = handle_message
BotContext.handle_poll_answer = handle_poll_answer

BotContext.setup_handlers = setup_handlers
BotContext.setup_middlewares = setup_middlewares

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
    context.setup_middlewares()
    context.run()
