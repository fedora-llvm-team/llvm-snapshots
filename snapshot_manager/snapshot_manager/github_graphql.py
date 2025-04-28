"""
GithubGraphQL
"""

import pathlib
from types import TracebackType
from typing import Any

import fnc
from requests import Session


class GithubGraphQL:
    """A lightweight Github GraphQL API client.

    In order to properly close the session, use this class as a context manager:

        with GithubGraphQL(token="<GITHUB_API_TOKEN>") as g:
            g.query_from_file(filename="query.graphql", variables=None)

    or call the close() method manually

        g = GithubGraphQL(token="<GITHUB_API_TOKEN>")
        g.close()
    """

    def __init__(
        self,
        token: str = "",
        endpoint: str = "https://api.github.com/graphql",
        raise_on_error: bool = False,
    ):
        """
        Creates a session with the given bearer `token` and `endpoint`.

        Args:
            token (str): Your personal access token in Github (see https://github.com/settings/tokens)
            endpoint (str): The endpoint to query GraphQL from
            raise_on_error (bool): If you want to raise an exception in case of an error
        """
        self.__endpoint = endpoint
        self.__token = token
        self.__encoding = "utf-8"
        self.__raise_on_error = raise_on_error
        self.__session = Session()
        self.__session.headers.update(
            {
                "Authorization": f"Bearer {self.__token}",
                # See https://graphql.org/learn/best-practices/#json-with-gzip
                "Accept-Encoding": "gzip",
                # See #
                # https://github.blog/2021-11-16-graphql-global-id-migration-update/
                "X-Github-Next-Global-ID": "1",
            }
        )

    @property
    def token(self) -> str:
        """Returns the bearer token."""
        return self.__token

    @property
    def encoding(self) -> str:
        """Returns the default encoding to be expected from query files."""
        return self.__encoding

    def run_from_file(
        self,
        filename: pathlib.Path | str,
        variables: dict[str, str | int] = dict(),
        raise_on_error: bool = False,
    ) -> Any:
        """
        Read the query/mutation from the given file and execute it with the variables
        applied. If not requested otherwise the plain result is returned.

        See also:
        https://docs.github.com/en/graphql/guides/forming-calls-with-graphql
        https://docs.github.com/en/graphql/overview/explorer

        Args:
            filename (str): The filename of the query/mutation file.
            variables (dict): The variables to be applied to the query/mutation.
            raise_on_error (bool): If you want to raise an exception in case of an error
        """
        with open(file=filename, encoding=self.encoding) as file_handle:
            query = file_handle.read()
        return self.run(
            query,
            variables,
        )

    def __enter__(self) -> "GithubGraphQL":
        return self

    # @property
    # def session_headers(self) -> CaseInsensitiveDict:
    #     """Returns the HTTP headers used for the session."""
    #     return self.__session.headers

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Closes the session."""
        self.__session.close()

    def run(
        self,
        query: str,
        variables: dict[str, str | int] = dict(),
        raise_on_error: bool = False,
    ) -> dict[Any, Any]:
        """
        Execute the query with the variables applied. If not requested otherwise
        the plain result is returned. If you want to raise an exception in case
        of an error you can set `raise_on_error` to `True`.

        Args:
            query (str): The GraphQL query.
            variables (dict): The variables to be applied to the query.
            raise_on_error (bool): If you want to raise an exception in case of an error

        Raises:
            RuntimeError: In case of an error when `raise_on_error` is `True`.

        Returns:
            Result: The result of the query. Inspect the result for errors!
        """
        req = self.__session.post(
            url=self.__endpoint, json={"query": query, "variables": variables}
        )
        req.raise_for_status()
        res = dict(req.json())
        if "errors" in res and (raise_on_error or self.__raise_on_error):
            raise RuntimeError(
                str(fnc.get("errors[0].message", res, default="GraphQL Error"))
            )
        return res
