# SQLModel-CRUD-Utilities
A set of CRUD utilities to expedite operations with SQLModel.

## Instructions

- Run `pip install sqlmodel_crud_utils` or add `sqlmodel_crud_utils` to your
  requirements files
- Declare the value for the `SQL_DIALECT` environmental variable. It can either
  be actively loaded within the environment or added to a `.env` file, courtesy
  of `dotenv`.
  - For a list of available native and 3rd party dialects, please see here: https://docs.sqlalchemy.org/en/20/dialects/#included-dialects

## Inspiration
The reason behind creating this package was to streamline the CRUD operations
across multiple personal and team-based projects that rely on SQLModel for its
ORM operations.

Because of existing commitments to SQLModel within the tech stack of multiple
projects, this package will be continuously supported and developed. A close eye
will be kept on the SQLModel's ongoing roadmap and eventual uplift to SQLAlchemy
2.0 and Pydantic 2.0.
## Development Roadmap
- [ ] Release working Alpha version
- [ ] Test across existing projects to ensure complete coverage
- [ ] 100% test coverage
- [ ] Complete autonomous CICD for on-demand testing and building

## Roadmap
- [ ] Alpha release
- [ ] Beta release
- [ ] Solicit community feedback
- [ ] 360 Development Review
