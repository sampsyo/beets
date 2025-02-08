import responses

from beets.test.helper import PluginTestCase
from beetsplug import embyupdate


class EmbyUpdateTest(PluginTestCase):
    plugin = "embyupdate"

    def setUp(self):
        super().setUp()

        self.config["emby"] = {
            "host": "localhost",
            "port": 8096,
            "username": "username",
            "password": "password",
        }

    def test_api_url_only_name(self):
        assert (
            embyupdate.api_url(
                self.config["emby"]["host"].get(),
                self.config["emby"]["port"].get(),
                "/Library/Refresh",
            )
            == "http://localhost:8096/Library/Refresh?format=json"
        )

    def test_api_url_http(self):
        assert (
            embyupdate.api_url(
                "http://localhost",
                self.config["emby"]["port"].get(),
                "/Library/Refresh",
            )
            == "http://localhost:8096/Library/Refresh?format=json"
        )

    def test_api_url_https(self):
        assert (
            embyupdate.api_url(
                "https://localhost",
                self.config["emby"]["port"].get(),
                "/Library/Refresh",
            )
            == "https://localhost:8096/Library/Refresh?format=json"
        )

    def test_password_data(self):
        assert embyupdate.password_data(
            self.config["emby"]["username"].get(),
            self.config["emby"]["password"].get(),
        ) == {
            "username": "username",
            "password": "5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8",
            "passwordMd5": "5f4dcc3b5aa765d61d8327deb882cf99",
        }

    def test_create_header_no_token(self):
        assert embyupdate.create_headers(
            "e8837bc1-ad67-520e-8cd2-f629e3155721"
        ) == {
            "x-emby-authorization": (
                "MediaBrowser "
                'UserId="e8837bc1-ad67-520e-8cd2-f629e3155721", '
                'Client="other", '
                'Device="beets", '
                'DeviceId="beets", '
                'Version="0.0.0"'
            )
        }

    def test_create_header_with_token(self):
        assert embyupdate.create_headers(
            "e8837bc1-ad67-520e-8cd2-f629e3155721", token="abc123"
        ) == {
            "x-emby-authorization": (
                "MediaBrowser "
                'UserId="e8837bc1-ad67-520e-8cd2-f629e3155721", '
                'Client="other", '
                'Device="beets", '
                'DeviceId="beets", '
                'Version="0.0.0"'
            ),
            "x-mediabrowser-token": "abc123",
        }

    @responses.activate
    def test_get_token(self):
        body = (
            '{"User":{"Name":"username", '
            '"ServerId":"1efa5077976bfa92bc71652404f646ec",'
            '"Id":"2ec276a2642e54a19b612b9418a8bd3b","HasPassword":true,'
            '"HasConfiguredPassword":true,'
            '"HasConfiguredEasyPassword":false,'
            '"LastLoginDate":"2015-11-09T08:35:03.6357440Z",'
            '"LastActivityDate":"2015-11-09T08:35:03.6665060Z",'
            '"Configuration":{"AudioLanguagePreference":"",'
            '"PlayDefaultAudioTrack":true,"SubtitleLanguagePreference":"",'
            '"DisplayMissingEpisodes":false,'
            '"DisplayUnairedEpisodes":false,'
            '"GroupMoviesIntoBoxSets":false,'
            '"DisplayChannelsWithinViews":[],'
            '"ExcludeFoldersFromGrouping":[],"GroupedFolders":[],'
            '"SubtitleMode":"Default","DisplayCollectionsView":true,'
            '"DisplayFoldersView":false,"EnableLocalPassword":false,'
            '"OrderedViews":[],"IncludeTrailersInSuggestions":true,'
            '"EnableCinemaMode":true,"LatestItemsExcludes":[],'
            '"PlainFolderViews":[],"HidePlayedInLatest":true,'
            '"DisplayChannelsInline":false},'
            '"Policy":{"IsAdministrator":true,"IsHidden":false,'
            '"IsDisabled":false,"BlockedTags":[],'
            '"EnableUserPreferenceAccess":true,"AccessSchedules":[],'
            '"BlockUnratedItems":[],'
            '"EnableRemoteControlOfOtherUsers":false,'
            '"EnableSharedDeviceControl":true,'
            '"EnableLiveTvManagement":true,"EnableLiveTvAccess":true,'
            '"EnableMediaPlayback":true,'
            '"EnableAudioPlaybackTranscoding":true,'
            '"EnableVideoPlaybackTranscoding":true,'
            '"EnableContentDeletion":false,'
            '"EnableContentDownloading":true,"EnableSync":true,'
            '"EnableSyncTranscoding":true,"EnabledDevices":[],'
            '"EnableAllDevices":true,"EnabledChannels":[],'
            '"EnableAllChannels":true,"EnabledFolders":[],'
            '"EnableAllFolders":true,"InvalidLoginAttemptCount":0,'
            '"EnablePublicSharing":true}},'
            '"SessionInfo":{"SupportedCommands":[],'
            '"QueueableMediaTypes":[],"PlayableMediaTypes":[],'
            '"Id":"89f3b33f8b3a56af22088733ad1d76b3",'
            '"UserId":"2ec276a2642e54a19b612b9418a8bd3b",'
            '"UserName":"username","AdditionalUsers":[],'
            '"ApplicationVersion":"Unknown version",'
            '"Client":"Unknown app",'
            '"LastActivityDate":"2015-11-09T08:35:03.6665060Z",'
            '"DeviceName":"Unknown device","DeviceId":"Unknown device id",'
            '"SupportsRemoteControl":false,"PlayState":{"CanSeek":false,'
            '"IsPaused":false,"IsMuted":false,"RepeatMode":"RepeatNone"}},'
            '"AccessToken":"4b19180cf02748f7b95c7e8e76562fc8",'
            '"ServerId":"1efa5077976bfa92bc71652404f646ec"}'
        )

        responses.add(
            responses.POST,
            ("http://localhost:8096" "/Users/AuthenticateByName"),
            body=body,
            status=200,
            content_type="application/json",
        )

        headers = {
            "x-emby-authorization": (
                "MediaBrowser "
                'UserId="e8837bc1-ad67-520e-8cd2-f629e3155721", '
                'Client="other", '
                'Device="beets", '
                'DeviceId="beets", '
                'Version="0.0.0"'
            )
        }

        auth_data = {
            "username": "username",
            "password": "5baa61e4c9b93f3f0682250b6cf8331b7ee68fd8",
            "passwordMd5": "5f4dcc3b5aa765d61d8327deb882cf99",
        }

        assert (
            embyupdate.get_token("http://localhost", 8096, headers, auth_data)
            == "4b19180cf02748f7b95c7e8e76562fc8"
        )

    @responses.activate
    def test_get_user(self):
        body = (
            '[{"Name":"username",'
            '"ServerId":"1efa5077976bfa92bc71652404f646ec",'
            '"Id":"2ec276a2642e54a19b612b9418a8bd3b","HasPassword":true,'
            '"HasConfiguredPassword":true,'
            '"HasConfiguredEasyPassword":false,'
            '"LastLoginDate":"2015-11-09T08:35:03.6357440Z",'
            '"LastActivityDate":"2015-11-09T08:42:39.3693220Z",'
            '"Configuration":{"AudioLanguagePreference":"",'
            '"PlayDefaultAudioTrack":true,"SubtitleLanguagePreference":"",'
            '"DisplayMissingEpisodes":false,'
            '"DisplayUnairedEpisodes":false,'
            '"GroupMoviesIntoBoxSets":false,'
            '"DisplayChannelsWithinViews":[],'
            '"ExcludeFoldersFromGrouping":[],"GroupedFolders":[],'
            '"SubtitleMode":"Default","DisplayCollectionsView":true,'
            '"DisplayFoldersView":false,"EnableLocalPassword":false,'
            '"OrderedViews":[],"IncludeTrailersInSuggestions":true,'
            '"EnableCinemaMode":true,"LatestItemsExcludes":[],'
            '"PlainFolderViews":[],"HidePlayedInLatest":true,'
            '"DisplayChannelsInline":false},'
            '"Policy":{"IsAdministrator":true,"IsHidden":false,'
            '"IsDisabled":false,"BlockedTags":[],'
            '"EnableUserPreferenceAccess":true,"AccessSchedules":[],'
            '"BlockUnratedItems":[],'
            '"EnableRemoteControlOfOtherUsers":false,'
            '"EnableSharedDeviceControl":true,'
            '"EnableLiveTvManagement":true,"EnableLiveTvAccess":true,'
            '"EnableMediaPlayback":true,'
            '"EnableAudioPlaybackTranscoding":true,'
            '"EnableVideoPlaybackTranscoding":true,'
            '"EnableContentDeletion":false,'
            '"EnableContentDownloading":true,'
            '"EnableSync":true,"EnableSyncTranscoding":true,'
            '"EnabledDevices":[],"EnableAllDevices":true,'
            '"EnabledChannels":[],"EnableAllChannels":true,'
            '"EnabledFolders":[],"EnableAllFolders":true,'
            '"InvalidLoginAttemptCount":0,"EnablePublicSharing":true}}]'
        )

        responses.add(
            responses.GET,
            "http://localhost:8096/Users/Public",
            body=body,
            status=200,
            content_type="application/json",
        )

        response = embyupdate.get_user("http://localhost", 8096, "username")

        assert response[0]["Id"] == "2ec276a2642e54a19b612b9418a8bd3b"

        assert response[0]["Name"] == "username"
