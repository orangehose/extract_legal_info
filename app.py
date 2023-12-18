from fastapi import FastAPI, Request, HTTPException
from xmltodict3 import XmlTextToDict
import re
from dateparser.search import search_dates

app = FastAPI()


async def dicts_merge(a, b):
    key = None

    if a is None or isinstance(a, str) or isinstance(a, int) or isinstance(a, float):
        a = b
    elif isinstance(a, list):
        if isinstance(b, list):
            a.extend(b)
        else:
            a.append(b)
    elif isinstance(a, dict):
        if isinstance(b, dict):
            for key in b:
                if key in a:
                    a[key] = await dicts_merge(a[key], b[key])
                else:
                    a[key] = b[key]
        else:
            return None
    else:
        return None
    return a


async def xml_to_dict(data):
    result = XmlTextToDict(data, ignore_namespace=True).get_dict()['root']['row']
    return result


# async def decode_body_utf_8(body):


async def date_normalize(data: dict):
    date_regex = "([1-9]|[12][0-9]|3[01]).(\w+).\\b([1-9]|[1-9][0-9]|[1-9][0-9][0-9]|[1-9][0-9][0-9][0-9])\\b"

    async def find_and_replace(dictionary, item, key, value):
        dates = re.search(pattern=date_regex, string=item)
        if dates:
            dates = dates.group()
            # recognize the date in Russian and convert it to the required format
            found_dates = search_dates(dates)
            if found_dates:
                for inner in range(len(found_dates)):
                    dictionary[key] = dictionary[key].replace(
                        value,
                        found_dates[inner][1].strftime('%d.%m.%Y')
                    )

    async def through_dict(d):
        for key, value in d.items():
            if isinstance(value, dict):
                await through_dict(value)
            elif isinstance(value, list):
                for item in value:
                    await find_and_replace(d, item, key, value)
            else:
                await find_and_replace(d, value, key, value)

    await through_dict(data)


async def term_normalize(data: dict):
    days_pattern = "\\b([1-9]|[1-9][0-9]|[1-9][0-9][0-9]|[1-9][0-9][0-9][0-9])\\b дн\S+"
    weeks_pattern = "\\b([1-9]|[1-9][0-9]|[1-9][0-9][0-9]|[1-9][0-9][0-9][0-9])\\b неде\S+"
    month_pattern = "\\b([1-9]|[1-9][0-9]|[1-9][0-9][0-9]|[1-9][0-9][0-9][0-9])\\b меся\S+"
    years_pattern = "\\b([1-9]|[1-9][0-9]|[1-9][0-9][0-9]|[1-9][0-9][0-9][0-9])\\b год"

    # russian = SpellChecker(language='ru')

    async def find_and_replace(dictionary, item, key, value):
        days = re.search(pattern=days_pattern, string=item)
        weeks = re.search(pattern=weeks_pattern, string=item)
        month = re.search(pattern=month_pattern, string=item)
        years = re.search(pattern=years_pattern, string=item)

        days_len = 0
        weeks_len = 0
        month_len = 0
        years_len = 0

        if days:
            days_len = [int(word) for word in days.group().split() if word.isdigit()][0]
        if weeks:
            weeks_len = [int(word) for word in weeks.group().split() if word.isdigit()][0]
        if month:
            month_len = [int(word) for word in month.group().split() if word.isdigit()][0]
        if years:
            years_len = [int(word) for word in years.group().split() if word.isdigit()][0]

        if days_len > 0 or weeks_len > 0 or month_len > 0 or years_len > 0:
            elements = [str(years_len), str(month_len), str(weeks_len), str(days_len)]
            dictionary[key] = dictionary[key].replace(days.group(), '_'.join(elements))

    async def through_dict(d):
        for key, value in d.items():
            if isinstance(value, dict):
                await through_dict(value)
            elif isinstance(value, list):
                for item in value:
                    await find_and_replace(d, item, key, value)
            else:
                await find_and_replace(d, value, key, value)

    await through_dict(data)


async def post_processing(data: list):
    result = {}
    for item in data:
        temp = await dicts_merge(result, item)
        result.update(temp)
    return result


@app.post('/get_legal_info')
async def read_data(request: Request):
    content_type = request.headers['Content-Type']
    if content_type == 'application/xml':
        body = await request.body()
        xml = await xml_to_dict(body.decode('utf-8'))
        result = await post_processing(xml)

        await date_normalize(result)
        await term_normalize(result)

        return result

    elif content_type == 'application/json':
        json = await request.json()
        result = await post_processing(json)

        await date_normalize(result)
        await term_normalize(result)

        return result
    else:
        raise HTTPException(status_code=400, detail=f'Content type {content_type} not supported')


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
