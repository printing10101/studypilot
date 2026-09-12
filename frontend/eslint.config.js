// ESLint 平面配置：类型安全交给 tsc（strict + noUnused*），这里聚焦正确性规则。
import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist/', 'node_modules/', 'src/.mimosa/'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // 项目仍基于 React 18 惯用写法（如 useState(Date.now())、effect 内同步复位子状态、
      // "latest ref" 转发 onClose）。set-state-in-effect / purity / refs 是面向
      // React Compiler 的新世界观规则，全面重构属于行为变更而非整洁性清理，
      // 待升级 React Compiler 时一并处理。
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/refs': 'off',
      // 类型边界的把关交给 tsc strict：项目大量使用受控 `catch (e: any)`，迁移成本高于收益
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      // 中文 UI 文案里的全角空格（如「　·　」分隔）是刻意的排版
      'no-irregular-whitespace': 'off',
    },
  },
)
