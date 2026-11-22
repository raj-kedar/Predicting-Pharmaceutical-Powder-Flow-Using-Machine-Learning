import { render } from 'preact';
import '../styles.css';
import './admin.css';
import { AdminApp } from './AdminApp';

render(<AdminApp />, document.getElementById('root')!);
