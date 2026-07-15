from enum import StrEnum


class CurrencyType(StrEnum):
    FIAT = "FIAT"
    CRYPTO = "CRYPTO"


class ExpenseType(StrEnum):
    eat = "EAT"
    transport = "TRANSPORT"
    travel = "TRAVEL"
    tooth = "TOOTH"
    subscribe = "SUBSCRIBE"
    rent = "RENT"
    sport = "SPORT"
    clothes = "CLOTHES"
    look = "LOOK"
    household = "HOUSEHOLD"
    cigarettes = "CIGARETTES"
    alcohol = "ALCOHOL"


class IncomingType(StrEnum):
    salary = "SALARY"
    percentage_of_the_deposit = "PERCENTAGEOFTHEDEPOSIT"
    part_time_job = "PARTTIMEJOB"
    gift = "GIFT"
