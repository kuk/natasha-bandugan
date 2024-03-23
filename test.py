
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
    Moder, ModerPred,
    BotContext,

    Voting,
    UserStats,

    CHAT_ID,
    ADMIN_ID,
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
        poll_id='-1',
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
    assert voting == await db.get_voting(voting.poll_id)

    await db.delete_voting(voting.poll_id)
    assert await db.get_voting(voting.poll_id) is None


async def test_db_user_stats(db):
    user_stats = UserStats(
        chat_id=-1,
        user_id=-1,
        message_count=1
    )

    await db.put_user_stats(user_stats)
    assert user_stats == await db.get_user_stats(user_stats.key)

    await db.delete_user_stats(user_stats.key)
    assert await db.get_user_stats(user_stats.key) is None


######
#
#   MODER
#
####


@pytest.fixture(scope='function')
async def moder():
    moder = Moder()
    await moder.connect()
    yield moder
    await moder.close()


async def test_moder(moder):
    pred = await moder.predict('добавляйся к нам в группу, зарабатывай на крипте зарабатывай на крипте зарабатывай на крипте')
    assert pred.is_spam
    assert pred.confidence > 0.5


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

    async def send_message(self, **kwargs):
        await self.request('sendMessage', kwargs)
        return Message(
            message_id=-1,
            chat=Chat(id=-1)
        )
    
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
            message_id=-1,
            poll=Poll(id='-1'),
            chat=Chat(id=-1),
        )


class FakeDB(DB):
    def __init__(self):
        DB.__init__(self)
        self.votings = []
        self.user_stats = []

    async def put_voting(self, obj):
        await self.delete_voting(obj.poll_id)
        self.votings.append(obj)

    async def get_voting(self, poll_id):
        for obj in self.votings:
            if obj.poll_id == poll_id:
                return obj

    async def delete_voting(self, poll_id):
        self.votings = [
            _ for _ in self.votings
            if _.poll_id != poll_id
        ]

    async def put_user_stats(self, obj):
        await self.delete_user_stats(obj.key)
        self.user_stats.append(obj)

    async def get_user_stats(self, key):
        for obj in self.user_stats:
            if obj.key == key:
                return obj

    async def delete_user_stats(self, key):
        self.user_stats = [
            _ for _ in self.user_stats
            if _.key != key
        ]


class FakeModer(Moder):
    def __init__(self):
        self.pred = ModerPred(
            is_spam=False,
            confidence=1.0
        )

    async def predict(self, text):
        return self.pred


class FakeBotContext(BotContext):
    def __init__(self):
        self.bot = FakeBot('1:token')
        self.dispatcher = Dispatcher(self.bot)
        self.db = FakeDB()
        self.moder = FakeModer()

    async def sleep(self, delay):
        pass


@pytest.fixture(scope='function')
def context():
    context = FakeBotContext()
    context.setup_handlers()
    context.setup_middlewares()

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


def my_chat_member_json(chat_id):
    return '{"my_chat_member": {"chat": {"id": %d, "title": "C", "type": "group", "all_members_are_administrators": true}, "from": {"id": -1, "is_bot": false, "first_name": "A", "last_name": "K", "username": "ak", "language_code": "ru"}, "date": 1711016747, "old_chat_member": {"user": {"id": -1, "is_bot": true, "first_name": "C", "username": "c"}, "status": "left"}, "new_chat_member": {"user": {"id": -3, "is_bot": true, "first_name": "C", "username": "c"}, "status": "member"}}}' % chat_id


def message_json(chat_id, text):
    return '{"message": {"message_id": -1, "from": {"id": -1, "is_bot": false, "first_name": "A", "last_name": "K", "username": "ak"}, "chat": {"id": %d, "title": "C", "username": "c", "type": "supergroup"}, "date": 1711091220, "text": "%s"}}' % (chat_id, text)


def reply_message_json(text):
    return '{"message": {"message_id": -1, "from": {"id": -1, "is_bot": false, "first_name": "A", "last_name": "K", "username": "ak", "language_code": "ru"}, "chat": {"id": %d, "title": "C", "username": "C", "type": "supergroup"}, "date": 1658923577, "reply_to_message": {"message_id": -1, "from": {"id": -1, "is_bot": false, "first_name": "A", "last_name": "K"}, "chat": {"id": -1, "title": "C", "username": "C", "type": "supergroup"}, "date": 1658923525, "text": "..."}, "text": "%s"}}' % (CHAT_ID, text)


def poll_answer_json(option_id):
    return '{"poll_answer": {"poll_id": "-1", "user": {"id": -1, "is_bot": false, "first_name": "A", "last_name": "K", "username": "ak", "language_code": "ru"}, "option_ids": [%d]}}' % option_id


async def test_leave_chat(context):
    await process_update(context, my_chat_member_json(CHAT_ID))
    await process_update(context, my_chat_member_json(-1))
    assert match_trace(context.bot.trace, [
        ['leaveChat', '{"chat_id": -1}']
    ])


async def test_pass(context):
    await process_update(context, message_json(CHAT_ID, 'не /voteban'))
    assert match_trace(context.bot.trace, [])

    await process_update(context, message_json(-1, '/voteban'))
    assert match_trace(context.bot.trace, [])


async def test_user_stats(context):
    await process_update(context, message_json(CHAT_ID, '...'))
    assert context.db.user_stats == [
        UserStats(chat_id=CHAT_ID, user_id=-1, message_count=1)
    ]


async def test_use_reply(context):
    await process_update(context, message_json(CHAT_ID, '/voteban'))
    assert match_trace(context.bot.trace, [
        ['sendMessage', '{"chat_id": %d, "text": "Напиши это в реплае на спам' % CHAT_ID],
        ['deleteMessage', '{"chat_id": %d, "message_id": -1}' % CHAT_ID],
        ['deleteMessage', '{"chat_id": -1, "message_id": -1}']
    ])
    

async def test_auto_delete(context):
    context.moder.pred.is_spam = True
    await process_update(context, message_json(CHAT_ID, 'крипто скамерский скам'))
    assert match_trace(context.bot.trace, [
        ['sendMessage', '{"chat_id": %d, "text": "moder ban, confidence=1.0"}' % ADMIN_ID],
        ['forwardMessage', '{"chat_id": %d, "from_chat_id": %d, "message_id": -1}' % (ADMIN_ID, CHAT_ID)]
    ])


async def test_start_voting(context):
    await process_update(context, reply_message_json('/voteban'))
    assert match_trace(context.bot.trace, [
        ['getChatMember', '{"chat_id": %d, "user_id": -1}' % CHAT_ID],
        ['sendPoll',  '{"chat_id": %d, "question": "Забанить' % CHAT_ID],
    ])
    assert context.db.votings == [
        Voting(
            poll_id='-1',
            chat_id=-1,
            candidate_message_id=-1,
            poll_message_id=-1,
            start_message_id=-1,
            starter_user_id=-1,
            candidate_user_id=-1,
            ban_user_ids=[],
            no_ban_user_ids=[],
            min_votes=10
        )
    ]


async def test_ban_admin(context):
    context.bot.admin_chat_member = True
    await process_update(context, reply_message_json('/voteban'))
    assert match_trace(context.bot.trace, [
        ['getChatMember', '{"chat_id": %d, "user_id": -1}' % CHAT_ID],
        ['sendMessage', '{"chat_id": %d, "text": "A K админ"' % CHAT_ID],
        ['deleteMessage', '{"chat_id": %d, "message_id": -1}' % CHAT_ID],
        ['deleteMessage', '{"chat_id": -1, "message_id": -1}'],
    ])


INIT_VOTING = Voting(
    poll_id='-1', chat_id=-1,
    candidate_message_id=2, poll_message_id=1, start_message_id=3,
    starter_user_id=-1, candidate_user_id=-2,
    ban_user_ids=[], no_ban_user_ids=[],
    min_votes=1
)


async def test_ban_vote(context):
    context.db.votings = [INIT_VOTING]
    await process_update(context, poll_answer_json(0))
    assert match_trace(context.bot.trace, [
        ['banChatMember', '{"chat_id": -1, "user_id": -2'],
        ['sendMessage', '{"chat_id": %d, "text": "voting ban"}' % ADMIN_ID],
        ['forwardMessage', '{"chat_id": %d, "from_chat_id": -1, "message_id": 2}' % ADMIN_ID],
        ['deleteMessage', '{"chat_id": -1, "message_id": 2}'],
        ['deleteMessage', '{"chat_id": -1, "message_id": 3}'],
        ['deleteMessage', '{"chat_id": -1, "message_id": 1}']
    ])
    voting = await context.db.get_voting(INIT_VOTING.poll_id)
    assert voting.ban_user_ids == [-1]


async def test_no_ban_vote(context):
    context.db.votings = [INIT_VOTING]
    await process_update(context, poll_answer_json(1))
    assert match_trace(context.bot.trace, [
        ['deleteMessage', '{"chat_id": -1, "message_id": 3}'],
        ['deleteMessage', '{"chat_id": -1, "message_id": 1}']
    ])
    voting = await context.db.get_voting(INIT_VOTING.poll_id)
    assert voting.no_ban_user_ids == [-1]


async def test_revote(context):
    context.db.votings = [
        replace(INIT_VOTING, min_votes=2)
    ]
    await process_update(context, poll_answer_json(0))
    await process_update(context, poll_answer_json(1))
    assert context.bot.trace == []
    voting = await context.db.get_voting(INIT_VOTING.poll_id)
    assert voting.ban_user_ids == []
    assert voting.no_ban_user_ids == [-1]
