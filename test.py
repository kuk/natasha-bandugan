
import asyncio
from json import (
    loads as parse_json,
    dumps as format_json
)
from dataclasses import replace

import pytest

from aiogram.types import (
    Update,
    Message,
    Poll,
    Chat,
    ChatMember,
)

from main import (
    Bot,
    Dispatcher,
    ChatMemberStatus,

    DB,
    BotContext,

    Voting,
)


######
#
#   DB
#
#####


# MAYBE FIXME scope='session' breaks is strange way

@pytest.fixture(scope='function')
async def db():
    db = DB()
    await db.connect()
    yield db
    await db.close()


async def test_db_votings(db):
    voting = Voting(
        poll_id='1',
        chat_id=-1,

        candidate_message_id=-1,
        start_message_id=-1,
        poll_message_id=-1,

        candidate_user_id=-1,
        starter_user_id=-1,

        ban_user_ids=[-1, -2],
        no_ban_user_ids=[-3, -4],
        min_votes=1
    )

    await db.put_voting(voting)
    assert voting == await db.get_voting(poll_id=voting.poll_id)

    await db.delete_voting(poll_id=voting.poll_id)
    assert await db.get_voting(poll_id=voting.poll_id) is None


#######
#
#  BOT
#
######


class FakeBot(Bot):
    def __init__(self, token):
        Bot.__init__(self, token)
        self.trace = []
        self.admin_chat_member = False

    async def request(self, method, data):
        json = format_json(data, ensure_ascii=False)
        self.trace.append([method, json])
        return {}

    async def get_chat_member(self, **kwargs):
        await self.request('getChatMember', kwargs)

        status = (
            ChatMemberStatus.ADMINISTRATOR
            if self.admin_chat_member
            else ChatMemberStatus.MEMBER
        )
        return ChatMember(status=status)

    async def send_poll(self, **kwargs):
        await self.request('sendPoll', kwargs)

        return Message(
            message_id=1,
            poll=Poll(id='123'),
            chat=Chat(id=123),
        )


class FakeDB(DB):
    def __init__(self):
        DB.__init__(self)
        self.votings = []

    async def put_voting(self, voting):
        await self.delete_voting(voting.poll_id)
        self.votings.append(voting)

    async def get_voting(self, poll_id):
        for voting in self.votings:
            if voting.poll_id == poll_id:
                return voting

    async def delete_voting(self, poll_id):
        self.votings = [
            _ for _ in self.votings
            if _.poll_id != poll_id
        ]


class FakeBotContext(BotContext):
    def __init__(self):
        self.bot = FakeBot('123:faketoken')
        self.dispatcher = Dispatcher(self.bot)
        self.db = FakeDB()


@pytest.fixture(scope='function')
def context():
    context = FakeBotContext()
    context.setup_handlers()

    Bot.set_current(context.bot)
    Dispatcher.set_current(context.dispatcher)

    return context


async def process_update(context, json):
    data = parse_json(json)
    update = Update(**data)
    await context.dispatcher.process_update(update)


def match_trace(trace, etalon):
    if len(trace) != len(etalon):
        return False

    for (method, json), (etalon_method, etalon_match) in zip(trace, etalon):
        if method != etalon_method:
            return False

        if etalon_match not in json:
            return False

    return True


START_VOTING_JSON = '{"message": {"message_id": 4, "from": {"id": 113947584, "is_bot": false, "first_name": "Alexander", "last_name": "Kukushkin", "username": "alexkuk", "language_code": "ru"}, "chat": {"id": -1001712750774, "title": "bandugan_bot_test_chat", "username": "bandugan_bot_test_chat", "type": "supergroup"}, "date": 1658923577, "reply_to_message": {"message_id": 3, "from": {"id": 5428138451, "is_bot": false, "first_name": "Alexander", "last_name": "Kukushkin"}, "chat": {"id": -1001712750774, "title": "bandugan_bot_test_chat", "username": "bandugan_bot_test_chat", "type": "supergroup"}, "date": 1658923525, "text": "abc"}, "text": "/voteban", "entities": [{"type": "bot_command", "offset": 0, "length": 8}]}}'


async def test_start_voting(context):
    await process_update(context, START_VOTING_JSON)
    assert match_trace(context.bot.trace, [
        ['getChatMember', '{"chat_id": -1001712750774, "user_id": 5428138451}'],
        ['sendPoll',  '{"chat_id": -1001712750774, "question": "Забанить'],
    ])
    assert context.db.votings == [
        Voting(poll_id='123', chat_id=123, candidate_message_id=3, poll_message_id=1, start_message_id=4, starter_user_id=113947584, candidate_user_id=5428138451, ban_user_ids=[], no_ban_user_ids=[], min_votes=10)
    ]


async def test_ban_admin(context):
    context.bot.admin_chat_member = True
    await process_update(context, START_VOTING_JSON)
    assert match_trace(context.bot.trace, [
        ['getChatMember', '{"chat_id": -1001712750774, "user_id": 5428138451}'],
        ['sendMessage', '{"chat_id": -1001712750774, "text": "Alexander Kukushkin админ"}']
    ])


VOTE_JSON = '{"poll_answer": {"poll_id": "123", "user": {"id": 113947584, "is_bot": false, "first_name": "Alexander", "last_name": "Kukushkin", "username": "alexkuk", "language_code": "ru"}, "option_ids": [0]}}'

INIT_VOTING = Voting(
    poll_id='123', chat_id=123,
    candidate_message_id=2, poll_message_id=1, start_message_id=4,
    starter_user_id=113947584, candidate_user_id=5428138451,
    ban_user_ids=[], no_ban_user_ids=[],
    min_votes=1
)


async def test_ban_vote(context):
    context.db.votings = [INIT_VOTING]
    await process_update(context, VOTE_JSON)
    assert match_trace(context.bot.trace, [
        ['banChatMember', '{"chat_id": 123, "user_id": 5428138451'],
        ['deleteMessage', '{"chat_id": 123, "message_id": 2}'],
        ['deleteMessage', '{"chat_id": 123, "message_id": 4}'],
        ['deleteMessage', '{"chat_id": 123, "message_id": 1}']
    ])
    voting = await context.db.get_voting(INIT_VOTING.poll_id)
    assert voting.ban_user_ids == [113947584]


async def test_no_ban_vote(context):
    context.db.votings = [INIT_VOTING]
    await process_update(context, VOTE_JSON.replace('[0]', '[1]'))
    assert match_trace(context.bot.trace, [
        ['deleteMessage', '{"chat_id": 123, "message_id": 4}'],
        ['deleteMessage', '{"chat_id": 123, "message_id": 1}']
    ])
    voting = await context.db.get_voting(INIT_VOTING.poll_id)
    assert voting.no_ban_user_ids == [113947584]


async def test_revote(context):
    context.db.votings = [
        replace(INIT_VOTING, min_votes=2)
    ]
    await process_update(context, VOTE_JSON)
    await process_update(context, VOTE_JSON.replace('[0]', '[1]'))
    assert context.bot.trace == []
    voting = await context.db.get_voting(INIT_VOTING.poll_id)
    assert voting.ban_user_ids == []
    assert voting.no_ban_user_ids == [113947584]
