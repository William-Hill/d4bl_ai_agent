# Contributing Guidelines

Thank you for your interest in contributing to the D4BL Research and Analysis Tool!

## Getting Started

1. Fork the repository
2. Clone your fork
3. Set up development environment (see [Development Guide](DEVELOPMENT.md))
4. Create a feature branch

## Development Process

1. **Create a branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**:
   - Write clean, readable code
   - Follow existing code style
   - Add comments where needed
   - Update documentation

3. **Test your changes**:
   - Test locally
   - Verify no regressions
   - Check for errors

4. **Commit your changes**:
   ```bash
   git commit -m "feat: add new feature"
   ```

5. **Push and create PR**:
   ```bash
   git push origin feature/your-feature-name
   ```

## Code Style

### Python

- Follow PEP 8
- Use type hints
- Maximum line length: 100 characters
- Use descriptive variable names
- Add docstrings for functions/classes

### TypeScript/React

- Use TypeScript
- Functional components with hooks
- Use meaningful component names
- Follow React best practices
- Use Tailwind CSS for styling

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `style:` Code style changes (formatting)
- `refactor:` Code refactoring
- `test:` Adding tests
- `chore:` Maintenance tasks

Example:
```
feat: add user authentication
fix: resolve WebSocket connection issue
docs: update API documentation
```

## Pull Request Process

1. **Update documentation** if needed
2. **Add tests** for new features
3. **Ensure all tests pass**
4. **Update CHANGELOG.md** (if applicable)
5. **Request review** from maintainers

## Areas for Contribution

- Bug fixes
- New features
- Documentation improvements
- Performance optimizations
- Test coverage
- UI/UX improvements
- API enhancements

## Questions?

Open an issue or start a discussion on GitHub.

Thank you for contributing! 🎉


