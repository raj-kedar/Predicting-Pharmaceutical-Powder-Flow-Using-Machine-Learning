import { render } from 'preact';
import './styles.css'; // must load before page styles, which build on it
import { App } from './App';

render(<App />, document.getElementById('root')!);
