
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

    CHAT_ID,
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

    async def send_message(self, **kwargs):
        await self.request('sendMessage', kwargs)
        return Message(
            message_id=1,
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
            message_id=1,
            poll=Poll(id='-1'),
            chat=Chat(id=-1),
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
        self.bot = FakeBot('1:faketoken')
        self.dispatcher = Dispatcher(self.bot)
        self.db = FakeDB()

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

        # json = json.replace(str(CHAT_ID), '-1')
        if etalon_match not in json:
            return False

    return True


def my_chat_member_json(chat_id):
    return '{"my_chat_member": {"chat": {"id": %d, "title": "test_bot_chat3", "type": "group", "all_members_are_administrators": true}, "from": {"id": 113947584, "is_bot": false, "first_name": "Alexander", "last_name": "Kukushkin", "username": "alexkuk", "language_code": "ru"}, "date": 1711016747, "old_chat_member": {"user": {"id": 5415060021, "is_bot": true, "first_name": "Bandugan", "username": "bandugan_bot"}, "status": "left"}, "new_chat_member": {"user": {"id": 5415060021, "is_bot": true, "first_name": "Bandugan", "username": "bandugan_bot"}, "status": "member"}}}' % chat_id


async def test_leave_chat(context):
    await process_update(context, my_chat_member_json(CHAT_ID))
    await process_update(context, my_chat_member_json(-1))
    assert match_trace(context.bot.trace, [
        ['leaveChat', '{"chat_id": -1}']
    ])


def message_json(chat_id, message_text):
    return '{"message": {"message_id": 91642, "from": {"id": 694057347, "is_bot": false, "first_name": "Bulat", "last_name": "Nurgatin", "username": "nurgatin_bn"}, "chat": {"id": %d, "title": "Natural Language Processing", "username": "natural_language_processing", "type": "supergroup"}, "date": 1711091220, "text": "%s"}}' % (chat_id, message_text)


async def test_pass(context):
    await process_update(context, message_json(CHAT_ID, 'не /voteban'))
    assert match_trace(context.bot.trace, [])

    await process_update(context, message_json(-1, '/voteban'))
    assert match_trace(context.bot.trace, [])


async def test_use_reply(context):
    await process_update(context, message_json(CHAT_ID, '/voteban'))
    assert match_trace(context.bot.trace, [
        ['sendMessage', '{"chat_id": %d, "text": "Напиши это в реплае на спам' % CHAT_ID],
        ['deleteMessage', '{"chat_id": %d, "message_id": 91642}' % CHAT_ID],
        ['deleteMessage', '{"chat_id": -1, "message_id": 1}']
    ])
    

def reply_message_json(message_text):
    return '{"message": {"message_id": 4, "from": {"id": 113947584, "is_bot": false, "first_name": "Alexander", "last_name": "Kukushkin", "username": "alexkuk", "language_code": "ru"}, "chat": {"id": %d, "title": "bandugan_bot_test_chat", "username": "bandugan_bot_test_chat", "type": "supergroup"}, "date": 1658923577, "reply_to_message": {"message_id": 3, "from": {"id": 5428138451, "is_bot": false, "first_name": "Alexander", "last_name": "Kukushkin"}, "chat": {"id": -1001712750774, "title": "bandugan_bot_test_chat", "username": "bandugan_bot_test_chat", "type": "supergroup"}, "date": 1658923525, "text": "abc"}, "text": "%s", "entities": [{"type": "bot_command", "offset": 0, "length": 8}]}}' % (CHAT_ID, message_text)


async def test_start_voting(context):
    await process_update(context, reply_message_json('/voteban'))
    assert match_trace(context.bot.trace, [
        ['getChatMember', '{"chat_id": %d, "user_id": 5428138451}' % CHAT_ID],
        ['sendPoll',  '{"chat_id": %d, "question": "Забанить' % CHAT_ID],
    ])
    assert context.db.votings == [
        Voting(poll_id='-1', chat_id=-1, candidate_message_id=3, poll_message_id=1, start_message_id=4, starter_user_id=113947584, candidate_user_id=5428138451, ban_user_ids=[], no_ban_user_ids=[], min_votes=10)
    ]


async def test_ban_admin(context):
    context.bot.admin_chat_member = True
    await process_update(context, reply_message_json('/voteban'))
    assert match_trace(context.bot.trace, [
        ['getChatMember', '{"chat_id": %d, "user_id": 5428138451}' % CHAT_ID],
        ['sendMessage', '{"chat_id": %d, "text": "Alexander Kukushkin админ"' % CHAT_ID],
        ['deleteMessage', '{"chat_id": %d, "message_id": 4}' % CHAT_ID],
        ['deleteMessage', '{"chat_id": -1, "message_id": 1}'],
    ])


def poll_answer_json(option_id):
    return '{"poll_answer": {"poll_id": "-1", "user": {"id": 113947584, "is_bot": false, "first_name": "Alexander", "last_name": "Kukushkin", "username": "alexkuk", "language_code": "ru"}, "option_ids": [%d]}}' % option_id

INIT_VOTING = Voting(
    poll_id='-1', chat_id=-1,
    candidate_message_id=2, poll_message_id=1, start_message_id=4,
    starter_user_id=113947584, candidate_user_id=5428138451,
    ban_user_ids=[], no_ban_user_ids=[],
    min_votes=1
)


async def test_ban_vote(context):
    context.db.votings = [INIT_VOTING]
    await process_update(context, poll_answer_json(0))
    assert match_trace(context.bot.trace, [
        ['banChatMember', '{"chat_id": -1, "user_id": 5428138451'],
        ['deleteMessage', '{"chat_id": -1, "message_id": 2}'],
        ['deleteMessage', '{"chat_id": -1, "message_id": 4}'],
        ['deleteMessage', '{"chat_id": -1, "message_id": 1}']
    ])
    voting = await context.db.get_voting(INIT_VOTING.poll_id)
    assert voting.ban_user_ids == [113947584]


async def test_no_ban_vote(context):
    context.db.votings = [INIT_VOTING]
    await process_update(context, poll_answer_json(1))
    assert match_trace(context.bot.trace, [
        ['deleteMessage', '{"chat_id": -1, "message_id": 4}'],
        ['deleteMessage', '{"chat_id": -1, "message_id": 1}']
    ])
    voting = await context.db.get_voting(INIT_VOTING.poll_id)
    assert voting.no_ban_user_ids == [113947584]


async def test_revote(context):
    context.db.votings = [
        replace(INIT_VOTING, min_votes=2)
    ]
    await process_update(context, poll_answer_json(0))
    await process_update(context, poll_answer_json(1))
    assert context.bot.trace == []
    voting = await context.db.get_voting(INIT_VOTING.poll_id)
    assert voting.ban_user_ids == []
    assert voting.no_ban_user_ids == [113947584]
