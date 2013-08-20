import os

from shutil import rmtree
from datetime import datetime
from curdling import CurdManager, Curd, hash_files

from sure import scenario
from mock import patch
from . import FIXTURE


def cleandir(context):
    for curd in os.listdir(FIXTURE('project1', '.curds')):
        rmtree(FIXTURE('project1', '.curds', curd))


@scenario(cleandir)
def test_hashing_files(context):
    "It should be possible to get a uniq hash that identifies a list of files"

    # Given that I have a list of files and a mocked content for each one
    file_list = (
        FIXTURE('project1', 'requirements.txt'),
        FIXTURE('project1', 'development.txt'),
    )

    # When I hash them
    hashed = hash_files(file_list)

    # Then I see that the hash is right
    hashed.should.equal('682f87d84c80d0a85c9179de681b3474906113b3')


def test_no_curd():
    "CurdManager.get() should return None when it can't find a specific curd"

    # Given that I have an instance of a curd manager
    curd_manager = CurdManager(FIXTURE('project1', '.curds'))

    # When I try to get a curd I know that does not exist
    curd = curd_manager.get('I-know-you-dont-exist')

    # Then I see it returns None
    curd.should.be.none


@scenario(cleandir)
def test_new_curd(context):
    "It should be possible to create new curds based on requirements files"

    # Given that I have a file that contains a list of dependencies of a fake
    # project
    curd_manager = CurdManager(
        FIXTURE('project1', '.curds'),
        {'index-url': 'http://localhost:8000/simple'})
    requirements = (
        FIXTURE('project1', 'requirements.txt'),
        FIXTURE('project1', 'development.txt'),
    )
    uid = hash_files(requirements)

    # When I create the new curd
    curd = curd_manager.new(requirements)

    # Then I see the curd was downloaded correctly created
    os.path.isdir(FIXTURE('project1', '.curds')).should.be.true
    os.path.isdir(FIXTURE('project1', '.curds', uid)).should.be.true

    (os.path.isfile(FIXTURE('project1', '.curds', uid, 'gherkin-0.1.0-py27-none-any.whl'))
        .should.be.true)
    (os.path.isfile(FIXTURE('project1', '.curds', uid, 'forbiddenfruit-0.1.0-py27-none-any.whl'))
        .should.be.true)


@scenario(cleandir)
def test_has_curd(context):
    "It should be possible to find curds saved locally"

    # Given that I have a curd hash, a curd manager linked to a curdcache
    curd_id = '682f87d84c80d0a85c9179de681b3474906113b3'
    path = FIXTURE('project1', '.curds')
    settings = {'index-url': 'http://localhost:8000/simple'}
    manager = CurdManager(path, settings)
    requirements = (
        FIXTURE('project1', 'requirements.txt'),
        FIXTURE('project1', 'development.txt'),
    )
    curd = manager.new(requirements)

    # When I retrieve the unknown curd
    curd = manager.get(curd.uid)

    # Then I see that my curd was properly retrieved
    curd.should.be.a(Curd)
    curd.uid.should.equal(curd_id)
    curd.path.should.equal(os.path.join(path, curd_id))

    # mocking the created prop
    with patch('os.stat') as stat:
        stat.return_value.st_ctime = 1376943600
        curd.created.should.equal(datetime(2013, 8, 19, 16, 20))


@scenario(cleandir)
def test_find_cached_curds(context):
    "It should be possible to find cached curds"

    # Given that I have a newly created curd
    curd_manager = CurdManager(
        FIXTURE('project1', '.curds'),
        {'index-url': 'http://localhost:8000/simple'})
    requirements = FIXTURE('project1', 'requirements.txt'),
    curd1 = curd_manager.new(requirements)

    # When I try to get the same curd instead of creating it
    with patch('curdling.pip') as pip:
        curd2 = curd_manager.new(requirements)

        # Then I see that the pip command was not called in the second time
        pip.wheel.called.should.be.false

    # Then I see curd1 and curd2 are just the same object
    curd1.should_not.be.none
    curd1.should.equal(curd2)


@scenario(cleandir)
def test_list_curds(context):
    "It should be possible to list available curds in a manager"

    # Given that I have a newly created curd
    manager = CurdManager(
        FIXTURE('project1', '.curds'),
        {'index-url': 'http://localhost:8000/simple'})
    curd1 = manager.new((FIXTURE('project1', 'requirements.txt'),))

    # When I list all the curds
    curds = manager.available()

    # Then I see that the curd1 that I just created is inside of the list
    curds.should.contain(curd1)
