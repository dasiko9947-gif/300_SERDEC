from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    name = State()
    partner_name = State()
    gender = State()           # ← НОВОЕ: пол
    start_date = State()
    tz = State()


class MovieFSM(StatesGroup):
    add_title = State()
    choose_for_today = State()
    right_title = State() 
    rate = State()
    random_pick = State() 


class WishFSM(StatesGroup):
    add_text = State()


class ShopFSM(StatesGroup):
    compliment_text = State()
    custom_wish = State()
    movie_choice = State()
    transfer_amount = State()


class SettingsFSM(StatesGroup):
    edit_nick = State()
    edit_time = State()
    add_date_title = State()
    add_date_value = State()


class GiftFSM(StatesGroup):    # ← НОВОЕ: письмо к подарку
    letter = State()
    